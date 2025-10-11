"""
AI Functions - FoodFlow
Funzioni basate su AI/LLM per suggerimenti intelligenti
"""

import os
import json
import requests
from datetime import datetime, timedelta
from flask import current_app
from dotenv import load_dotenv

# Carica variabili d'ambiente dal file .env
load_dotenv()

from .models import Product, NutritionalProfile, MealPlan, NutritionalGoal, UserStats, User

# ========================================
# CONSTANTS
# ========================================

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.7


# ========================================
# AI RECIPE SUGGESTIONS
# ========================================

def suggest_recipes(user_id, max_recipes=5, servings=None):
    """
    Suggerisce ricette basate su ingredienti disponibili
    
    Args:
        user_id: ID utente
        max_recipes: Numero massimo ricette
    
    Returns:
        list: Ricette con formato standardizzato
    """
    try:
        # Recupera prodotti disponibili
        products = Product.query.filter_by(user_id=user_id, wasted=False).all()
        
        if not products:
            return []
        
        # Formatta ingredienti
        ingredients = [(p.name, p.quantity, p.unit) for p in products]
        
        # Genera ricette con AI
        recipes = ai_generate_recipe_suggestions(ingredients, user_id, max_recipes)
        # Fallback se AI non restituisce nulla
        if not recipes:
            return _generate_fallback_recipes(products[:5], max_recipes)

        # Filtra per allergie e restrizioni utente
        try:
            restrictions, allergies = _get_user_restrictions_and_allergies(user_id)
            if restrictions or allergies:
                filtered = []
                for recipe in recipes:
                    if not _recipe_violates_preferences(recipe, restrictions, allergies):
                        filtered.append(recipe)
                recipes = filtered
        except Exception as _:
            # In caso di problemi col profilo, proseguiamo senza filtrare
            pass
        
        # Arricchisci, scala porzioni e normalizza unità
        for recipe in recipes:
            if 'nutritional_info' not in recipe:
                recipe['nutritional_info'] = _estimate_nutrition_fallback()
            if 'tips' not in recipe:
                recipe['tips'] = ["Segui le istruzioni con attenzione"]
            if 'dietary_tags' not in recipe:
                recipe['dietary_tags'] = []
            # Scala per porzioni se richiesto
            if servings is not None:
                _scale_recipe_servings(recipe, servings)
            # Normalizza unità ingredienti
            _normalize_recipe_units(recipe)
        # Rimappa unità verso quelle della dispensa dell'utente quando possibile
        _remap_recipe_units_to_pantry(recipes, user_id)
        
        return recipes
        
    except Exception as e:
        current_app.logger.error(f"suggest_recipes error: {e}")
        try:
            return _generate_fallback_recipes(products[:5], max_recipes)
        except Exception:
            return []


def ai_generate_recipe_suggestions(ingredients, user_id=None, max_recipes=5):
    """
    Genera ricette usando Groq AI
    
    Args:
        ingredients: lista di tuple (nome, quantità, unità)
        user_id: ID utente per personalizzazione
        max_recipes: numero ricette da generare
    
    Returns:
        list: Ricette in formato JSON
    """
    try:
        api_key = os.getenv('GROQ_API_KEY')
        
        if not api_key:
            current_app.logger.error("GROQ_API_KEY not configured")
            return []
        
        if not ingredients:
            return []
        
        # Recupera preferenze utente
        dietary_info = _get_user_dietary_info(user_id) if user_id else "Nessuna preferenza"
        restrictions, allergies = _get_user_restrictions_and_allergies(user_id) if user_id else (set(), set())
        
        # Formatta ingredienti per prompt
        ingredients_text = "\n".join([
            f"- {qty} {unit} di {name}" 
            for name, qty, unit in ingredients
        ])
        
        # Prepara prompt
        system_prompt = """Sei uno chef esperto. Genera ricette in formato JSON valido.
Formato richiesto:
{
  "recipes": [
    {
      "name": "Nome Ricetta",
      "ingredients": [
        {"item": "ingrediente", "quantity": 100, "unit": "g"}
      ],
      "instructions": ["passo 1", "passo 2"],
      "prep_time": 15,
      "cooking_time": 30,
      "difficulty": "easy",
      "servings": 2,
      "nutritional_info": {
        "per_serving": {
          "calories": 350,
          "protein": 20,
          "carbs": 40,
          "fat": 12,
          "fiber": 8
        }
      },
      "dietary_tags": ["vegetarian"],
      "tips": ["consiglio utile"]
    }
  ]
}"""
        
        user_prompt = f"""Ingredienti disponibili:
{ingredients_text}

Preferenze utente:
{dietary_info}

Genera {max_recipes} ricette creative che:
1. Usano principalmente questi ingredienti
2. Rispettano le preferenze dietetiche
3. Sono bilanciate nutrizionalmente
4. Hanno istruzioni chiare e dettagliate

CONSTRAINT IMPORTANTI:
- Evita QUALSIASI ingrediente che corrisponda a queste allergie (case-insensitive, sinonimi comuni): {', '.join(sorted(allergies)) if allergies else 'nessuna'}
- Rispetta queste restrizioni dietetiche e includile in dietary_tags: {', '.join(sorted(restrictions)) if restrictions else 'nessuna'}

Rispondi SOLO con JSON valido."""
        
        # Chiamata API
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": DEFAULT_MAX_TOKENS,
                "temperature": DEFAULT_TEMPERATURE
            },
            timeout=30
        )
        
        if response.status_code != 200:
            current_app.logger.error(f"Groq API error: {response.status_code} - {response.text}")
            return []
        
        # Parse response
        try:
            payload = response.json()
        except Exception as e:
            current_app.logger.error(f"Groq API invalid JSON: {e}; body={response.text[:500]}")
            return []
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            current_app.logger.warning("Groq API empty content")
            return []
        
        # Estrai JSON (gestisce markdown code blocks)
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Prova a trovare un blocco JSON tra backticks o parentesi
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(content[start:end+1])
                except Exception as e:
                    raise e
            else:
                raise
        
        # Estrai ricette
        if isinstance(data, dict) and "recipes" in data:
            return data["recipes"]
        elif isinstance(data, list):
            return data
        else:
            current_app.logger.warning("Unexpected AI response format")
            return []
        
    except json.JSONDecodeError as e:
        current_app.logger.error(f"JSON parse error: {e}")
        return []
    except requests.Timeout:
        current_app.logger.error("Groq API timeout")
        return []
    except Exception as e:
        current_app.logger.error(f"ai_generate_recipe_suggestions error: {e}")
        return []


# ========================================
# MEAL PLANNING AI
# ========================================

def ai_optimize_meal_planning(user_id, days=7):
    """
    Genera piano pasti settimanale ottimizzato usando AI
    
    Args:
        user_id: ID utente
        days: Giorni da pianificare
    
    Returns:
        dict: Piano pasti per giorni {day: [meals]}
    """
    try:
        # Recupera profilo nutrizionale
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        goals = NutritionalGoal.query.filter_by(user_id=user_id).first()
        
        # Recupera ingredienti disponibili
        products = Product.query.filter_by(user_id=user_id, wasted=False).all()
        
        if not products:
            return _generate_basic_meal_plan(days)
        
        # Genera piano con AI
        meal_plan = ai_generate_weekly_meal_plan(user_id, profile, goals, products, days)
        
        if not meal_plan:
            return _generate_basic_meal_plan(days)
        
        return meal_plan
        
    except Exception as e:
        current_app.logger.error(f"ai_optimize_meal_planning error: {e}")
        return _generate_basic_meal_plan(days)


def ai_generate_weekly_meal_plan(user_id, profile, goals, products, days=7):
    """
    Genera piano pasti settimanale usando Groq AI
    
    Args:
        user_id: ID utente
        profile: Profilo nutrizionale
        goals: Obiettivi nutrizionali
        products: Prodotti disponibili
        days: Giorni da pianificare
    
    Returns:
        dict: Piano pasti strutturato
    """
    try:
        api_key = os.getenv('GROQ_API_KEY')
        
        if not api_key:
            current_app.logger.error("GROQ_API_KEY not configured")
            return _generate_basic_meal_plan(days)
        
        # Prepara dati per AI
        ingredients_text = "\n".join([
            f"- {p.name} ({p.quantity} {p.unit})" 
            for p in products[:20]  # Limita per prompt
        ])
        
        # Info nutrizionali
        nutritional_info = ""
        if goals:
            nutritional_info = f"""
Obiettivi nutrizionali giornalieri:
- Calorie: {goals.daily_calories}
- Proteine: {goals.daily_protein}g
- Carboidrati: {goals.daily_carbs}g
- Grassi: {goals.daily_fat}g
- Fibre: {goals.daily_fiber}g
"""
        
        # Info profilo
        profile_info = ""
        if profile:
            profile_info = f"""
Profilo utente:
- Età: {profile.age} anni
- Peso: {profile.weight} kg
- Altezza: {profile.height} cm
- Genere: {profile.gender}
- Livello attività: {profile.activity_level}
- Obiettivo: {profile.goal}
"""
        
        # Restrizioni dietetiche
        restrictions = ""
        if profile and profile.dietary_restrictions:
            try:
                restrictions_list = json.loads(profile.dietary_restrictions)
                if restrictions_list:
                    restrictions = f"Restrizioni dietetiche: {', '.join(restrictions_list)}\n"
            except:
                pass
        
        # Allergie
        allergies = ""
        if profile and profile.allergies:
            try:
                allergies_list = json.loads(profile.allergies)
                if allergies_list:
                    allergies = f"Allergie: {', '.join(allergies_list)}\n"
            except:
                pass
        
        # Prompt per AI
        system_prompt = """Sei un nutrizionista esperto e chef professionista. 
Genera un piano pasti settimanale bilanciato in formato JSON.

Formato richiesto:
{
  "meal_plan": {
    "monday": [
      {"meal_type": "breakfast", "name": "Nome pasto", "description": "Descrizione dettagliata", "calories": 400, "protein": 20, "carbs": 50, "fat": 15},
      {"meal_type": "lunch", "name": "Nome pasto", "description": "Descrizione dettagliata", "calories": 600, "protein": 30, "carbs": 60, "fat": 20},
      {"meal_type": "dinner", "name": "Nome pasto", "description": "Descrizione dettagliata", "calories": 500, "protein": 25, "carbs": 40, "fat": 18},
      {"meal_type": "snack", "name": "Nome pasto", "description": "Descrizione dettagliata", "calories": 200, "protein": 10, "carbs": 25, "fat": 8}
    ],
    "tuesday": [...],
    ...
  }
}

REGOLE IMPORTANTI:
1. Usa principalmente gli ingredienti disponibili
2. Bilanciare i macronutrienti giornalieri
3. Variare i pasti per evitare monotonia
4. Rispettare restrizioni e allergie
5. Includere sempre: colazione, pranzo, cena, spuntino
6. Calorie totali giornaliere devono essere vicine agli obiettivi
7. Descrizioni devono essere dettagliate e pratiche
8. Nomi pasti devono essere appetitosi e chiari

Rispondi SOLO con JSON valido."""
        
        user_prompt = f"""Genera un piano pasti per {days} giorni.

{profile_info}
{nutritional_info}
{restrictions}
{allergies}

Ingredienti disponibili:
{ingredients_text}

Crea un piano variato, bilanciato e pratico che:
- Usa principalmente gli ingredienti disponibili
- Rispetta gli obiettivi nutrizionali
- Include varietà per evitare monotonia
- È realizzabile con gli ingredienti a disposizione
- Considera le restrizioni dietetiche e allergie

Rispondi SOLO con JSON valido."""
        
        # Chiamata API
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 3000,
                "temperature": 0.7
            },
            timeout=30
        )
        
        if response.status_code != 200:
            current_app.logger.error(f"Groq API error: {response.status_code} - {response.text}")
            return _generate_basic_meal_plan(days)
        
        # Parse response
        try:
            payload = response.json()
        except Exception as e:
            current_app.logger.error(f"Groq API invalid JSON: {e}; body={response.text[:500]}")
            return _generate_basic_meal_plan(days)
        
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            current_app.logger.warning("Groq API empty content")
            return _generate_basic_meal_plan(days)
        
        # Estrai JSON
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        try:
            data = json.loads(content)
            meal_plan = data.get("meal_plan", {})
            
            if not meal_plan:
                return _generate_basic_meal_plan(days)
            
            # Valida e normalizza struttura
            return _validate_and_normalize_meal_plan(meal_plan, days)
            
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Invalid JSON from AI: {e}; content: {content[:500]}")
            return _generate_basic_meal_plan(days)
        
    except Exception as e:
        current_app.logger.error(f"ai_generate_weekly_meal_plan error: {e}")
        return _generate_basic_meal_plan(days)


def _validate_and_normalize_meal_plan(meal_plan, days):
    """Valida e normalizza il piano pasti generato dall'AI"""
    try:
        days_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        normalized = {}
        
        for day_name, meals in meal_plan.items():
            if day_name.lower() in days_map and isinstance(meals, list):
                day_index = days_map[day_name.lower()]
                if day_index < days:
                    normalized[day_index] = []
                    
                    for meal in meals:
                        if isinstance(meal, dict) and 'meal_type' in meal:
                            # Normalizza meal
                            normalized_meal = {
                                'meal_type': meal.get('meal_type', 'lunch'),
                                'name': meal.get('name', 'Pasto'),
                                'description': meal.get('description', ''),
                                'calories': max(0, meal.get('calories', 0)),
                                'protein': max(0, meal.get('protein', 0)),
                                'carbs': max(0, meal.get('carbs', 0)),
                                'fat': max(0, meal.get('fat', 0))
                            }
                            normalized[day_index].append(normalized_meal)
        
        return normalized
        
    except Exception as e:
        current_app.logger.error(f"_validate_and_normalize_meal_plan error: {e}")
        return _generate_basic_meal_plan(days)


def _generate_basic_meal_plan(days=7):
    """Genera piano pasti base (fallback)"""
    meal_templates = {
        'breakfast': [
            {'name': 'Omelette con verdure', 'description': 'Omelette con pomodori, spinaci e formaggio', 'calories': 350, 'protein': 20, 'carbs': 8, 'fat': 25},
            {'name': 'Porridge con frutta', 'description': 'Avena con banana, mirtilli e miele', 'calories': 300, 'protein': 12, 'carbs': 45, 'fat': 8},
            {'name': 'Yogurt con granola', 'description': 'Yogurt greco con granola e frutti di bosco', 'calories': 280, 'protein': 15, 'carbs': 35, 'fat': 10}
        ],
        'lunch': [
            {'name': 'Insalata di pollo', 'description': 'Insalata mista con petto di pollo grigliato', 'calories': 450, 'protein': 35, 'carbs': 20, 'fat': 25},
            {'name': 'Pasta integrale', 'description': 'Pasta integrale con pomodoro e basilico', 'calories': 400, 'protein': 15, 'carbs': 60, 'fat': 12},
            {'name': 'Riso con verdure', 'description': 'Riso integrale con verdure miste al vapore', 'calories': 380, 'protein': 12, 'carbs': 65, 'fat': 8}
        ],
        'dinner': [
            {'name': 'Salmone al forno', 'description': 'Salmone con patate e broccoli al vapore', 'calories': 500, 'protein': 40, 'carbs': 35, 'fat': 20},
            {'name': 'Pollo alla griglia', 'description': 'Petto di pollo con quinoa e verdure', 'calories': 450, 'protein': 45, 'carbs': 30, 'fat': 15},
            {'name': 'Pesce spada', 'description': 'Pesce spada con riso e insalata', 'calories': 420, 'protein': 35, 'carbs': 40, 'fat': 18}
        ],
        'snack': [
            {'name': 'Frutta fresca', 'description': 'Mela con mandorle', 'calories': 150, 'protein': 4, 'carbs': 20, 'fat': 8},
            {'name': 'Yogurt greco', 'description': 'Yogurt greco con noci', 'calories': 120, 'protein': 10, 'carbs': 8, 'fat': 6},
            {'name': 'Smoothie', 'description': 'Smoothie con banana e spinaci', 'calories': 180, 'protein': 6, 'carbs': 25, 'fat': 5}
        ]
    }
    
    meal_plan = {}
    for day in range(days):
        day_meals = []
        for meal_type in ['breakfast', 'lunch', 'dinner', 'snack']:
            import random
            template = random.choice(meal_templates[meal_type])
            meal = {
                'meal_type': meal_type,
                'name': template['name'],
                'description': template['description'],
                'calories': template['calories'],
                'protein': template['protein'],
                'carbs': template['carbs'],
                'fat': template['fat']
            }
            day_meals.append(meal)
        meal_plan[day] = day_meals
    
    return meal_plan


# ========================================
# SHOPPING LIST AI
# ========================================

def ai_suggest_shopping_list(user_id):
    """
    Genera suggerimenti intelligenti per lista spesa
    
    Returns:
        dict: {suggestions: [product_names]}
    """
    try:
        # Prodotti in scadenza (3 giorni)
        expiring = Product.query.filter(
            Product.user_id == user_id,
            Product.expiry_date <= datetime.utcnow().date() + timedelta(days=3),
            Product.wasted == False
        ).all()
        
        # Prodotti in esaurimento
        low_stock = Product.query.filter(
            Product.user_id == user_id,
            Product.quantity <= Product.min_quantity,
            Product.wasted == False
        ).all()
        
        # Unisci e deduplica
        suggestions = list(set([p.name for p in expiring + low_stock]))
        
        return {
            'success': True,
            'suggestions': suggestions,
            'total': len(suggestions)
        }
        
    except Exception as e:
        current_app.logger.error(f"ai_suggest_shopping_list error: {e}")
        return {'success': False, 'suggestions': []}


# ========================================
# NUTRITION ANALYSIS
# ========================================

def analyze_meal_plan_nutrition(meal_plan_id):
    """
    Analizza valori nutrizionali di un meal plan
    
    Returns:
        dict: Analisi nutrizionale
    """
    try:
        meal_plan = MealPlan.query.get(meal_plan_id)
        
        if not meal_plan:
            return None
        
        # Se ha già i dati, ritornali
        if all([meal_plan.calories, meal_plan.protein, meal_plan.carbs, meal_plan.fat]):
            return {
                'calories': meal_plan.calories,
                'protein': meal_plan.protein,
                'carbs': meal_plan.carbs,
                'fat': meal_plan.fat,
                'fiber': meal_plan.fiber or 0,
                'balance_score': _calculate_balance_score(meal_plan)
            }
        
        # Altrimenti stima
        return {
            'calories': 500,
            'protein': 30,
            'carbs': 60,
            'fat': 20,
            'fiber': 10,
            'balance_score': 75
        }
        
    except Exception as e:
        current_app.logger.error(f"analyze_meal_plan_nutrition error: {e}")
        return None


# ========================================
# HELPER FUNCTIONS (PRIVATE)
# ========================================

def _get_user_dietary_info(user_id):
    """Recupera info dietetiche utente"""
    try:
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            return "Nessuna preferenza specificata"
        
        info_parts = []
        
        if profile.goal:
            goal_map = {
                'lose_weight': 'Perdita peso',
                'gain_weight': 'Aumento peso',
                'maintain': 'Mantenimento',
                'muscle_gain': 'Aumento massa muscolare'
            }
            info_parts.append(f"Obiettivo: {goal_map.get(profile.goal, profile.goal)}")
        
        if profile.activity_level:
            info_parts.append(f"Attività: {profile.activity_level}")
        
        if profile.dietary_restrictions:
            try:
                restrictions = json.loads(profile.dietary_restrictions)
                if restrictions:
                    info_parts.append(f"Restrizioni: {', '.join(restrictions)}")
            except:
                pass
        
        if profile.allergies:
            try:
                allergies = json.loads(profile.allergies)
                if allergies:
                    info_parts.append(f"Allergie: {', '.join(allergies)}")
            except:
                pass
        
        return "\n".join(info_parts) if info_parts else "Nessuna preferenza specificata"
        
    except Exception as e:
        current_app.logger.error(f"Error getting dietary info: {e}")
        return "Errore recupero preferenze"


def _normalize_token(value):
    """Normalizza stringhe per confronto naive."""
    if not value:
        return ""
    return str(value).strip().lower()


def _get_user_restrictions_and_allergies(user_id):
    """Ritorna (restrictions_set, allergies_set) dal profilo nutrizionale."""
    restrictions_set = set()
    allergies_set = set()
    profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
    if profile:
        if profile.dietary_restrictions:
            try:
                for r in json.loads(profile.dietary_restrictions) or []:
                    token = _normalize_token(r)
                    if token:
                        restrictions_set.add(token)
            except Exception:
                pass
        if profile.allergies:
            try:
                for a in json.loads(profile.allergies) or []:
                    token = _normalize_token(a)
                    if token:
                        allergies_set.add(token)
            except Exception:
                pass
    return restrictions_set, allergies_set


def _recipe_violates_preferences(recipe, restrictions, allergies):
    """True se la ricetta viola allergie/restrizioni dell'utente."""
    try:
        # Check allergie sugli ingredienti
        if allergies:
            for ing in (recipe.get('ingredients') or []):
                item_name = _normalize_token((ing or {}).get('item'))
                if not item_name:
                    continue
                for allergen in allergies:
                    if allergen and allergen in item_name:
                        return True

        # Check restrizioni usando dietary_tags se presenti
        if restrictions:
            tags = {_normalize_token(t) for t in (recipe.get('dietary_tags') or [])}
            if tags:
                # Richiedi che tutte le restrizioni compaiano nei tag
                missing = [r for r in restrictions if r not in tags]
                if missing:
                    return True
            # Se non ci sono tag, non scartare automaticamente per evitare falsi positivi
        return False
    except Exception:
        return False


def _estimate_nutrition_fallback():
    """Valori nutrizionali di fallback"""
    return {
        'per_serving': {
            'calories': 350,
            'protein': 20,
            'carbs': 45,
            'fat': 12,
            'fiber': 8
        }
    }


def _generate_fallback_recipes(products, max_recipes=3):
    """Genera ricette base se AI fallisce"""
    recipes = []
    
    for i in range(min(max_recipes, len(products), 3)):
        recipes.append({
            'name': f'Ricetta con {products[i].name}',
            'ingredients': [
                {
                    'item': p.name,
                    'quantity': p.quantity,
                    'unit': p.unit
                }
                for p in products[i:i+3]
            ],
            'instructions': [
                'Prepara gli ingredienti',
                'Combina secondo preferenza',
                'Cuoci a temperatura media',
                'Servi caldo'
            ],
            'prep_time': 15,
            'cooking_time': 30,
            'difficulty': 'easy',
            'servings': 2,
            'nutritional_info': _estimate_nutrition_fallback(),
            'dietary_tags': [],
            'tips': ['Ricetta generata automaticamente']
        })
    
    return recipes


def ai_estimate_meal_calories(meal_description, meal_type='lunch'):
    """
    Stima le calorie di un pasto usando AI
    
    Args:
        meal_description: Descrizione del pasto
        meal_type: Tipo di pasto (breakfast, lunch, dinner, snack)
    
    Returns:
        dict: {calories, protein, carbs, fat, fiber}
    """
    try:
        api_key = os.getenv('GROQ_API_KEY')
        
        if not api_key:
            # Fallback senza AI
            return _estimate_calories_fallback(meal_type)
        
        # Prompt per AI
        prompt = f"""
Analizza questo pasto e stima i valori nutrizionali:

Pasto: {meal_description}
Tipo: {meal_type}

Rispondi SOLO con un JSON valido nel formato:
{{
    "calories": numero,
    "protein": numero,
    "carbs": numero,
    "fat": numero,
    "fiber": numero
}}

Stima realistica basata su porzioni normali per {meal_type}.
"""

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'model': 'llama-3.1-70b-versatile',
            'temperature': 0.3,
            'max_tokens': 200
        }
        
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            # Estrai JSON dalla risposta
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                nutrition_data = json.loads(json_match.group())
                return {
                    'calories': int(nutrition_data.get('calories', 0)),
                    'protein': float(nutrition_data.get('protein', 0)),
                    'carbs': float(nutrition_data.get('carbs', 0)),
                    'fat': float(nutrition_data.get('fat', 0)),
                    'fiber': float(nutrition_data.get('fiber', 0))
                }
        
        # Fallback se AI non funziona
        return _estimate_calories_fallback(meal_type)
        
    except Exception as e:
        current_app.logger.error(f"ai_estimate_meal_calories error: {e}")
        return _estimate_calories_fallback(meal_type)


def _estimate_calories_fallback(meal_type):
    """Stima calorie di base senza AI"""
    base_calories = {
        'breakfast': 400,
        'lunch': 600,
        'dinner': 700,
        'snack': 200
    }
    
    calories = base_calories.get(meal_type, 500)
    
    return {
        'calories': calories,
        'protein': calories * 0.25 / 4,  # 25% proteine
        'carbs': calories * 0.50 / 4,     # 50% carboidrati
        'fat': calories * 0.25 / 9,       # 25% grassi
        'fiber': calories * 0.02          # 2% fibre
    }


def _calculate_balance_score(meal_plan):
    """Calcola score bilanciamento (0-100)"""
    if not all([meal_plan.protein, meal_plan.carbs, meal_plan.fat]):
        return 0
    
    # Proporzioni ideali: 30% proteine, 50% carbs, 20% grassi
    total_cals = (meal_plan.protein * 4) + (meal_plan.carbs * 4) + (meal_plan.fat * 9)
    
    if total_cals == 0:
        return 0
    
    protein_pct = (meal_plan.protein * 4 / total_cals) * 100
    carbs_pct = (meal_plan.carbs * 4 / total_cals) * 100
    fat_pct = (meal_plan.fat * 9 / total_cals) * 100
    
    # Deviazione da ideale
    protein_dev = abs(protein_pct - 30)
    carbs_dev = abs(carbs_pct - 50)
    fat_dev = abs(fat_pct - 20)
    
    total_dev = protein_dev + carbs_dev + fat_dev
    
    # Score: meno deviazione = score più alto
    score = max(0, 100 - total_dev)
    
    return round(score, 0)


# ========================================
# RECYCLING SUGGESTIONS AI
# ========================================

def ai_suggest_food_recycling(expired_products, user_id=None):
    """
    Suggerisce modi per riciclare/riutilizzare cibo scaduto usando AI
    
    Args:
        expired_products: Lista di prodotti scaduti
        user_id: ID utente per personalizzazione
    
    Returns:
        dict: Suggerimenti di riciclo per ogni prodotto
    """
    try:
        api_key = os.getenv('GROQ_API_KEY')
        
        if not api_key:
            current_app.logger.error("GROQ_API_KEY not configured")
            return _generate_fallback_recycling_suggestions(expired_products)
        
        if not expired_products:
            return {'success': True, 'suggestions': []}
        
        # Prepara lista prodotti scaduti
        products_text = "\n".join([
            f"- {p.name} (categoria: {p.category}, quantità: {p.quantity} {p.unit})" 
            for p in expired_products
        ])
        
        # Recupera preferenze utente se disponibili
        dietary_info = _get_user_dietary_info(user_id) if user_id else "Nessuna preferenza specificata"
        
        # Prompt per AI
        system_prompt = """Sei un esperto di sostenibilità alimentare e riciclo. 
Genera suggerimenti pratici per riciclare/riutilizzare cibo scaduto in formato JSON.

Formato richiesto:
{
  "suggestions": [
    {
      "product_name": "Nome Prodotto",
      "recycling_options": [
        {
          "type": "donation",
          "title": "Donazione a Canile",
          "description": "Descrizione dettagliata",
          "instructions": ["passo 1", "passo 2"],
          "benefits": ["beneficio 1", "beneficio 2"],
          "contact_info": "Info contatto se disponibile",
          "requirements": "Requisiti specifici"
        },
        {
          "type": "composting",
          "title": "Compostaggio",
          "description": "Come compostare questo prodotto",
          "instructions": ["passo 1", "passo 2"],
          "benefits": ["beneficio 1", "beneficio 2"],
          "requirements": "Requisiti per compostaggio"
        },
        {
          "type": "reuse",
          "title": "Riutilizzo Creativo",
          "description": "Idee per riutilizzare",
          "instructions": ["passo 1", "passo 2"],
          "benefits": ["beneficio 1", "beneficio 2"],
          "requirements": "Materiali necessari"
        }
      ]
    }
  ]
}

REGOLE IMPORTANTI:
1. Fornisci suggerimenti pratici e realizzabili
2. Includi sempre opzioni di donazione (canili, centri, banchi alimentari)
3. Suggerisci compostaggio per prodotti organici
4. Proponi riutilizzi creativi quando appropriato
5. Includi informazioni di contatto locali quando possibile
6. Considera la sicurezza alimentare
7. Sii specifico e dettagliato nelle istruzioni

Rispondi SOLO con JSON valido."""
        
        user_prompt = f"""Prodotti scaduti da riciclare:
{products_text}

Preferenze utente:
{dietary_info}

Genera suggerimenti di riciclo per ogni prodotto. Includi:
- Donazioni a canili, centri di recupero, banchi alimentari
- Compostaggio per prodotti organici
- Riutilizzi creativi (es. bucce per cosmetici, ossa per brodo)
- Informazioni su centri di raccolta locali
- Istruzioni dettagliate per ogni opzione

Sii pratico e considera la situazione italiana."""

        # Chiamata API
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 3000,
                "temperature": 0.7
            },
            timeout=30
        )
        
        if response.status_code != 200:
            current_app.logger.error(f"Groq API error: {response.status_code} - {response.text}")
            return _generate_fallback_recycling_suggestions(expired_products)
        
        # Parse response
        try:
            payload = response.json()
        except Exception as e:
            current_app.logger.error(f"Groq API invalid JSON: {e}; body={response.text[:500]}")
            return _generate_fallback_recycling_suggestions(expired_products)
        
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            current_app.logger.warning("Groq API empty content")
            return _generate_fallback_recycling_suggestions(expired_products)
        
        # Estrai JSON
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        try:
            data = json.loads(content)
            suggestions = data.get("suggestions", [])
            
            # Valida e arricchisci i suggerimenti
            return _validate_and_enrich_recycling_suggestions(suggestions, expired_products)
            
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Invalid JSON from AI: {e}; content: {content[:500]}")
            return _generate_fallback_recycling_suggestions(expired_products)
        
    except Exception as e:
        current_app.logger.error(f"ai_suggest_food_recycling error: {e}")
        return _generate_fallback_recycling_suggestions(expired_products)


def _validate_and_enrich_recycling_suggestions(suggestions, expired_products):
    """Valida e arricchisce i suggerimenti di riciclo"""
    try:
        enriched_suggestions = []
        
        for suggestion in suggestions:
            if not isinstance(suggestion, dict) or 'product_name' not in suggestion:
                continue
                
            product_name = suggestion.get('product_name', '')
            recycling_options = suggestion.get('recycling_options', [])
            
            # Trova il prodotto corrispondente
            matching_product = None
            for product in expired_products:
                if product.name.lower() == product_name.lower():
                    matching_product = product
                    break
            
            if not matching_product:
                continue
            
            # Valida e arricchisci le opzioni
            valid_options = []
            for option in recycling_options:
                if not isinstance(option, dict) or 'type' not in option:
                    continue
                
                # Normalizza l'opzione
                normalized_option = {
                    'type': option.get('type', 'reuse'),
                    'title': option.get('title', 'Opzione di Riciclo'),
                    'description': option.get('description', ''),
                    'instructions': option.get('instructions', []),
                    'benefits': option.get('benefits', []),
                    'contact_info': option.get('contact_info', ''),
                    'requirements': option.get('requirements', ''),
                    'icon': _get_recycling_icon(option.get('type', 'reuse')),
                    'priority': _get_recycling_priority(option.get('type', 'reuse'))
                }
                
                valid_options.append(normalized_option)
            
            if valid_options:
                enriched_suggestions.append({
                    'product': matching_product,
                    'product_name': product_name,
                    'recycling_options': valid_options
                })
        
        return {
            'success': True,
            'suggestions': enriched_suggestions,
            'total_products': len(enriched_suggestions)
        }
        
    except Exception as e:
        current_app.logger.error(f"_validate_and_enrich_recycling_suggestions error: {e}")
        return _generate_fallback_recycling_suggestions(expired_products)


def _generate_fallback_recycling_suggestions(expired_products):
    """Genera suggerimenti di base se AI non funziona"""
    try:
        suggestions = []
        
        for product in expired_products:
            recycling_options = []
            
            # Suggerimenti generici basati sulla categoria
            if product.category.lower() in ['verdura', 'frutta', 'ortaggi']:
                recycling_options.extend([
                    {
                        'type': 'composting',
                        'title': 'Compostaggio',
                        'description': 'Trasforma in compost per il giardino',
                        'instructions': [
                            'Taglia in pezzi piccoli',
                            'Aggiungi al compost o seppellisci nel terreno',
                            'Mescola con materiale secco (foglie, cartone)'
                        ],
                        'benefits': ['Fertilizzante naturale', 'Riduce rifiuti', 'Migliora il suolo'],
                        'contact_info': '',
                        'requirements': 'Area per compostaggio o giardino',
                        'icon': 'bi-recycle',
                        'priority': 'high'
                    },
                    {
                        'type': 'donation',
                        'title': 'Donazione a Canile',
                        'description': 'Alcune verdure possono essere donate agli animali',
                        'instructions': [
                            'Contatta canili locali',
                            'Verifica quali verdure accettano',
                            'Porta in giornata per evitare ulteriore deterioramento'
                        ],
                        'benefits': ['Aiuta animali bisognosi', 'Riduce sprechi'],
                        'contact_info': 'Cerca "canili" + nome della tua città',
                        'requirements': 'Contatto preventivo con il canile',
                        'icon': 'bi-heart',
                        'priority': 'medium'
                    }
                ])
            
            elif product.category.lower() in ['pane', 'pasta', 'cereali']:
                recycling_options.extend([
                    {
                        'type': 'reuse',
                        'title': 'Pane Raffermo - Croutons',
                        'description': 'Trasforma il pane raffermo in croutons',
                        'instructions': [
                            'Taglia il pane a cubetti',
                            'Tosta in forno a 180°C per 10-15 minuti',
                            'Conserva in contenitore ermetico'
                        ],
                        'benefits': ['Snack croccante', 'Non sprechi nulla'],
                        'contact_info': '',
                        'requirements': 'Forno e contenitore ermetico',
                        'icon': 'bi-lightbulb',
                        'priority': 'high'
                    },
                    {
                        'type': 'donation',
                        'title': 'Banco Alimentare',
                        'description': 'Donazione a organizzazioni caritatevoli',
                        'instructions': [
                            'Contatta banchi alimentari locali',
                            'Verifica orari di consegna',
                            'Porta prodotti ancora commestibili'
                        ],
                        'benefits': ['Aiuta famiglie bisognose', 'Riduce sprechi'],
                        'contact_info': 'Cerca "banco alimentare" + nome della tua città',
                        'requirements': 'Contatto preventivo',
                        'icon': 'bi-heart',
                        'priority': 'high'
                    }
                ])
            
            else:
                # Suggerimenti generici
                recycling_options.extend([
                    {
                        'type': 'donation',
                        'title': 'Centro di Raccolta Alimentare',
                        'description': 'Donazione a centri specializzati',
                        'instructions': [
                            'Cerca centri di raccolta alimentare locali',
                            'Verifica cosa accettano',
                            'Porta i prodotti in giornata'
                        ],
                        'benefits': ['Aiuta la comunità', 'Riduce sprechi'],
                        'contact_info': 'Cerca "raccolta alimentare" + nome della tua città',
                        'requirements': 'Contatto preventivo',
                        'icon': 'bi-heart',
                        'priority': 'medium'
                    }
                ])
            
            if recycling_options:
                suggestions.append({
                    'product': product,
                    'product_name': product.name,
                    'recycling_options': recycling_options
                })
        
        return {
            'success': True,
            'suggestions': suggestions,
            'total_products': len(suggestions)
        }
        
    except Exception as e:
        current_app.logger.error(f"_generate_fallback_recycling_suggestions error: {e}")
        return {'success': False, 'suggestions': []}


def _get_recycling_icon(recycling_type):
    """Restituisce icona appropriata per tipo di riciclo"""
    icon_map = {
        'donation': 'bi-heart',
        'composting': 'bi-recycle',
        'reuse': 'bi-lightbulb',
        'repair': 'bi-tools',
        'exchange': 'bi-arrow-left-right'
    }
    return icon_map.get(recycling_type, 'bi-arrow-clockwise')


def _get_recycling_priority(recycling_type):
    """Restituisce priorità per tipo di riciclo"""
    priority_map = {
        'donation': 'high',
        'composting': 'high',
        'reuse': 'medium',
        'repair': 'low',
        'exchange': 'medium'
    }
    return priority_map.get(recycling_type, 'medium')


# ========================================
# CHATBOT AI FUNCTIONS
# ========================================

def ai_chatbot_response(user_message, user_id, conversation_context=None):
    """
    Genera risposta del chatbot usando AI
    
    Args:
        user_message: Messaggio dell'utente
        user_id: ID utente per personalizzazione
        conversation_context: Contesto della conversazione
    
    Returns:
        dict: Risposta del chatbot con tipo e contenuto
    """
    try:
        api_key = os.getenv('GROQ_API_KEY')
        
        if not api_key:
            current_app.logger.error("GROQ_API_KEY not configured")
            return _generate_fallback_chat_response(user_message)
        
        # Recupera dati utente per contesto
        user_context = _get_user_chat_context(user_id)
        
        # Prepara contesto conversazione
        context_text = ""
        if conversation_context:
            context_text = f"\nContesto conversazione:\n{conversation_context}"
        
        # Prompt per AI
        system_prompt = """Sei FoodFlowBot, l'assistente intelligente di FoodFlow, un'app per la gestione della dispensa e la riduzione degli sprechi alimentari.

Il tuo ruolo è aiutare gli utenti con:
1. Gestione della dispensa (prodotti, scadenze, scorte)
2. Suggerimenti di ricette basate su ingredienti disponibili
3. Consigli per ridurre gli sprechi alimentari
4. Suggerimenti di riciclo per cibo scaduto
5. Consigli nutrizionali e obiettivi dietetici
6. Analytics e statistiche personali
7. Uso delle funzionalità dell'app

REGOLE IMPORTANTI:
- Sii sempre utile, amichevole e professionale
- Fornisci risposte pratiche e actionable
- Usa emoji appropriati per rendere la conversazione più vivace
- Se non hai informazioni specifiche, chiedi chiarimenti
- Suggerisci sempre azioni concrete che l'utente può fare
- Mantieni le risposte concise ma complete
- Usa un tono italiano colloquiale ma rispettoso

Formato risposta:
{
  "response": "Risposta testuale",
  "type": "text|suggestion|action|recipe|recycling",
  "suggestions": ["suggerimento1", "suggerimento2"],
  "actions": [
    {
      "text": "Testo azione",
      "url": "/path",
      "icon": "bi-icon-name"
    }
  ],
  "data": {} // Dati aggiuntivi se necessari
}

Rispondi SOLO con JSON valido."""

        user_prompt = f"""Messaggio utente: {user_message}

{user_context}
{context_text}

Rispondi come FoodFlowBot, fornendo aiuto specifico e pratico per la gestione alimentare."""

        # Chiamata API
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 1000,
                "temperature": 0.7
            },
            timeout=30
        )
        
        if response.status_code != 200:
            current_app.logger.error(f"Groq API error: {response.status_code} - {response.text}")
            return _generate_fallback_chat_response(user_message)
        
        # Parse response
        try:
            payload = response.json()
        except Exception as e:
            current_app.logger.error(f"Groq API invalid JSON: {e}; body={response.text[:500]}")
            return _generate_fallback_chat_response(user_message)
        
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            current_app.logger.warning("Groq API empty content")
            return _generate_fallback_chat_response(user_message)
        
        # Estrai JSON
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        try:
            data = json.loads(content)
            return _validate_chat_response(data)
            
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Invalid JSON from AI: {e}; content: {content[:500]}")
            return _generate_fallback_chat_response(user_message)
        
    except Exception as e:
        current_app.logger.error(f"ai_chatbot_response error: {e}")
        return _generate_fallback_chat_response(user_message)


def _get_user_chat_context(user_id):
    """Recupera contesto utente per il chatbot"""
    try:
        context_parts = []
        
        # Profilo nutrizionale
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        if profile:
            context_parts.append(f"Profilo: {profile.age} anni, {profile.weight}kg, {profile.height}cm, {profile.gender}")
            if profile.goal:
                context_parts.append(f"Obiettivo: {profile.goal}")
            if profile.activity_level:
                context_parts.append(f"Attività: {profile.activity_level}")
        
        # Prodotti in dispensa
        products = Product.query.filter_by(user_id=user_id, wasted=False).all()
        if products:
            expiring = [p for p in products if p.is_expiring_soon]
            low_stock = [p for p in products if p.is_low_stock]
            
            context_parts.append(f"Dispensa: {len(products)} prodotti totali")
            if expiring:
                context_parts.append(f"Prodotti in scadenza: {', '.join([p.name for p in expiring[:5]])}")
            if low_stock:
                context_parts.append(f"Scorte basse: {', '.join([p.name for p in low_stock[:5]])}")
        
        # Statistiche recenti
        stats = UserStats.query.filter_by(user_id=user_id).first()
        if stats:
            context_parts.append(f"Punti: {stats.points}, Livello: {stats.level}")
            context_parts.append(f"Prodotti aggiunti: {stats.total_products_added}, Sprechi: {stats.total_products_wasted}")
        
        return "\n".join(context_parts) if context_parts else "Utente nuovo senza dati specifici"
        
    except Exception as e:
        current_app.logger.error(f"_get_user_chat_context error: {e}")
        return "Contesto utente non disponibile"


def _validate_chat_response(data):
    """Valida e normalizza la risposta del chatbot"""
    try:
        return {
            'success': True,
            'response': data.get('response', 'Mi dispiace, non ho capito. Puoi riformulare la domanda?'),
            'type': data.get('type', 'text'),
            'suggestions': data.get('suggestions', []),
            'actions': data.get('actions', []),
            'data': data.get('data', {}),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        current_app.logger.error(f"_validate_chat_response error: {e}")
        return _generate_fallback_chat_response("")


def _generate_fallback_chat_response(user_message):
    """Genera risposta di fallback se AI non funziona"""
    try:
        message_lower = user_message.lower()
        
        # Risposte predefinite basate su parole chiave
        if any(word in message_lower for word in ['ricetta', 'cucinare', 'pasto']):
            return {
                'success': True,
                'response': '🍳 Per suggerimenti di ricette, vai alla sezione "Ricette AI" nella dashboard! Posso aiutarti a trovare ricette basate sui tuoi ingredienti disponibili.',
                'type': 'suggestion',
                'suggestions': ['Vai alle ricette AI', 'Mostra ingredienti disponibili'],
                'actions': [
                    {'text': 'Vai alle Ricette', 'url': '/', 'icon': 'bi-magic'}
                ],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['scadenza', 'scaduto', 'scade']):
            return {
                'success': True,
                'response': '📅 Controlla la sezione "Dispensa" per vedere i prodotti in scadenza. Posso anche suggerirti come riciclare il cibo scaduto!',
                'type': 'suggestion',
                'suggestions': ['Vai alla dispensa', 'Suggerimenti di riciclo'],
                'actions': [
                    {'text': 'Vai alla Dispensa', 'url': '/products', 'icon': 'bi-box-seam'},
                    {'text': 'Suggerimenti Riciclo', 'url': '/recycling-suggestions', 'icon': 'bi-recycle'}
                ],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['riciclo', 'riciclare', 'spreco']):
            return {
                'success': True,
                'response': '♻️ Ottima domanda! Vai alla sezione "Suggerimenti di Riciclo" per scoprire come trasformare il cibo scaduto in risorse preziose.',
                'type': 'action',
                'suggestions': ['Vai ai suggerimenti di riciclo'],
                'actions': [
                    {'text': 'Suggerimenti Riciclo', 'url': '/recycling-suggestions', 'icon': 'bi-recycle'}
                ],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['aiuto', 'help', 'come funziona']):
            return {
                'success': True,
                'response': '👋 Ciao! Sono FoodFlowBot, il tuo assistente per la gestione alimentare. Posso aiutarti con ricette, gestione dispensa, suggerimenti di riciclo e molto altro! Cosa vorresti sapere?',
                'type': 'text',
                'suggestions': ['Come funziona la dispensa', 'Suggerimenti di ricette', 'Ridurre gli sprechi'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        else:
            return {
                'success': True,
                'response': '🤔 Interessante! Posso aiutarti con la gestione della dispensa, ricette, suggerimenti di riciclo e molto altro. Cosa vorresti fare?',
                'type': 'text',
                'suggestions': ['Gestisci dispensa', 'Trova ricette', 'Suggerimenti riciclo', 'Vedi analytics'],
                'actions': [
                    {'text': 'Dispensa', 'url': '/products', 'icon': 'bi-box-seam'},
                    {'text': 'Ricette', 'url': '/', 'icon': 'bi-magic'},
                    {'text': 'Riciclo', 'url': '/recycling-suggestions', 'icon': 'bi-recycle'},
                    {'text': 'Analytics', 'url': '/analytics', 'icon': 'bi-graph-up'}
                ],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
            
    except Exception as e:
        current_app.logger.error(f"_generate_fallback_chat_response error: {e}")
        return {
            'success': False,
            'response': 'Mi dispiace, si è verificato un errore. Riprova più tardi!',
            'type': 'text',
            'suggestions': [],
            'actions': [],
            'data': {},
            'timestamp': datetime.now().isoformat()
        }


# ========================================
# UNITS & SERVINGS HELPERS
# ========================================

_UNIT_ALIASES = {
    'g': ['g', 'grammo', 'grammi'],
    'kg': ['kg', 'chilogrammo', 'chilogrammi'],
    'ml': ['ml', 'millilitro', 'millilitri'],
    'l': ['l', 'litro', 'litri'],
    'pz': ['pz', 'pezzo', 'pezzi', 'unit', 'unita']
}

_SPOON_MAP_TO_ML = {
    'cucchiaino': 5,
    'cucchiaino/i': 5,
    'tsp': 5,
    'cucchiaio': 15,
    'cucchiaio/i': 15,
    'tbsp': 15
}

def _normalize_unit_name(unit):
    u = (unit or '').strip().lower()
    if not u:
        return ''
    if u in _SPOON_MAP_TO_ML:
        return 'ml'
    for canon, aliases in _UNIT_ALIASES.items():
        if u == canon or u in aliases:
            return canon
    return u


def _convert_to_canonical_quantity(quantity, unit):
    """Converte quantità in unità canoniche (g, ml, pz, kg, l)."""
    try:
        q = float(quantity or 0)
    except Exception:
        q = 0.0
    u = _normalize_unit_name(unit)
    if u in ('cucchiaio', 'cucchiaino', 'tsp', 'tbsp'):
        # intercettato prima, ma per sicurezza
        ml = _SPOON_MAP_TO_ML.get(u, 0)
        return float(q * ml), 'ml'
    # Converti secondarie in primarie
    if u == 'kg':
        return q * 1000.0, 'g'
    if u == 'l':
        return q * 1000.0, 'ml'
    return q, u


def _scale_recipe_servings(recipe, target_servings):
    try:
        servings = recipe.get('servings') or 1
        servings = max(1, int(servings))
        target = max(1, int(target_servings))
        if target == servings:
            return
        ratio = target / servings
        for ing in (recipe.get('ingredients') or []):
            try:
                ing['quantity'] = round(float(ing.get('quantity') or 0) * ratio, 2)
            except Exception:
                pass
        recipe['servings'] = target
    except Exception:
        pass


def _normalize_recipe_units(recipe):
    try:
        for ing in (recipe.get('ingredients') or []):
            qty, unit = _convert_to_canonical_quantity(ing.get('quantity'), ing.get('unit'))
            ing['quantity'] = round(qty, 2)
            ing['unit'] = unit
    except Exception:
        pass


def _remap_recipe_units_to_pantry(recipes, user_id):
    """Se in dispensa un prodotto simile usa un'altra unità equivalente, prova ad allineare.
    Esempio: dispensa ha Latte in 'ml' e ricetta produce 'l' → normalizzato a 'ml'.
    """
    try:
        from .models import Product
        products = Product.query.filter_by(user_id=user_id, wasted=False).all()
        name_to_unit = {}
        for p in products:
            key = (p.name or '').strip().lower()
            if key and p.unit:
                name_to_unit[key] = _normalize_unit_name(p.unit)
        for recipe in recipes:
            for ing in (recipe.get('ingredients') or []):
                key = (ing.get('item') or '').strip().lower()
                if not key:
                    continue
                pantry_unit = name_to_unit.get(key)
                if not pantry_unit:
                    continue
                # Converte quantità dell'ingrediente nell'unità della dispensa se compatibile
                qty, unit = _convert_to_canonical_quantity(ing.get('quantity'), ing.get('unit'))
                # Se la dispensa usa g e noi siamo in ml, non convertiamo
                if pantry_unit == unit:
                    ing['quantity'] = round(qty, 2)
                    ing['unit'] = pantry_unit
                else:
                    # Prova conversioni inverse (g<->kg, ml<->l)
                    if pantry_unit == 'g' and unit == 'kg':
                        ing['quantity'] = round(qty * 1000.0, 2)
                        ing['unit'] = 'g'
                    elif pantry_unit == 'ml' and unit == 'l':
                        ing['quantity'] = round(qty * 1000.0, 2)
                        ing['unit'] = 'ml'
                    else:
                        # Mantieni unità normalizzate, non forziamo mapping non sicuri
                        ing['quantity'] = round(qty, 2)
                        ing['unit'] = unit
    except Exception:
        pass