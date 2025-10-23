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
# AI INGREDIENT EXTRACTION
# ========================================

def ai_extract_ingredients(meal_description):
    """
    Estrae ingredienti strutturati da testo libero con AI.
    Ritorna lista di dict: {item, quantity, unit}
    """
    try:
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            # Senza AI, ritorna vuoto per far usare il parser locale
            return []

        system_prompt = """Sei un assistente culinario. Estrai ingredienti da testo libero.
Respondi SOLO con JSON valido:
{
  "ingredients": [
    {"item": "nome", "quantity": numero, "unit": "unità"}
  ]
}
Regole:
- Usa unità semplici: g, kg, ml, l, pz, tsp, tbsp, cup
- quantity sempre numero (decimali ammessi con punto)
- item senza quantità o unità non devono essere inclusi
- Se non trovi quantità/unità, ometti quell'ingrediente
"""

        user_prompt = f"""Testo pasto:
{meal_description}

Estrai solo ingredienti con quantità e unità."""

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
                "max_tokens": 600,
                "temperature": 0.2
            },
            timeout=20
        )

        if response.status_code != 200:
            current_app.logger.error(f"Groq AI extract ingredients error: {response.status_code} - {response.text}")
            return []

        payload = response.json()
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            return []
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)
        ings = data.get('ingredients', []) if isinstance(data, dict) else []
        normalized = []
        for ing in ings:
            name = (ing.get('item') or '').strip()
            try:
                qty = float(ing.get('quantity') or 0)
            except Exception:
                qty = 0.0
            unit = (ing.get('unit') or '').strip().lower()
            if name and qty > 0 and unit:
                normalized.append({'item': name, 'quantity': qty, 'unit': unit})
        return normalized
    except Exception as e:
        current_app.logger.error(f"ai_extract_ingredients error: {e}")
        return []


# ========================================
# MEAL PLANNING AI
# ========================================

def _get_family_nutritional_constraints(user_id):
    """
    Raccoglie allergie e restrizioni dietetiche di tutti i membri della famiglia
    
    Args:
        user_id: ID dell'utente
    
    Returns:
        dict: Dizionario con allergie e restrizioni aggregate della famiglia
    """
    try:
        from .smart_functions import get_user_family
        from .models import User
        
        family = get_user_family(user_id)
        if not family:
            return {'allergies': [], 'restrictions': [], 'members_count': 1, 'members_info': []}
        
        all_allergies = set()
        all_restrictions = set()
        members_info = []
        
        # Itera sui membri della famiglia
        for member in family.members:
            user = User.query.get(member.user_id)
            if not user:
                continue
            
            profile = NutritionalProfile.query.filter_by(user_id=user.id).first()
            if not profile:
                continue
            
            # Aggiungi info membro
            member_data = {'name': user.username}
            
            # Raccogli allergie
            if profile.allergies:
                try:
                    member_allergies = json.loads(profile.allergies)
                    if member_allergies:
                        all_allergies.update(member_allergies)
                        member_data['allergies'] = member_allergies
                except:
                    pass
            
            # Raccogli restrizioni
            if profile.dietary_restrictions:
                try:
                    member_restrictions = json.loads(profile.dietary_restrictions)
                    if member_restrictions:
                        all_restrictions.update(member_restrictions)
                        member_data['restrictions'] = member_restrictions
                except:
                    pass
            
            if 'allergies' in member_data or 'restrictions' in member_data:
                members_info.append(member_data)
        
        return {
            'allergies': sorted(list(all_allergies)),
            'restrictions': sorted(list(all_restrictions)),
            'members_count': family.members.count(),
            'members_info': members_info
        }
        
    except Exception as e:
        current_app.logger.error(f"_get_family_nutritional_constraints error: {e}")
        return {'allergies': [], 'restrictions': [], 'members_count': 1, 'members_info': []}


def ai_optimize_meal_planning(user_id, days=7, share_with_family=False):
    """
    Genera piano pasti settimanale ottimizzato usando AI
    
    Args:
        user_id: ID utente
        days: Giorni da pianificare
        share_with_family: Se True, considera i vincoli nutrizionali di tutta la famiglia
    
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
        
        # Genera piano con AI considerando eventualmente i vincoli della famiglia
        meal_plan = ai_generate_weekly_meal_plan(user_id, profile, goals, products, days, share_with_family)
        
        if not meal_plan:
            return _generate_basic_meal_plan(days)
        
        return meal_plan
        
    except Exception as e:
        current_app.logger.error(f"ai_optimize_meal_planning error: {e}")
        return _generate_basic_meal_plan(days)

def ai_generate_weekly_meal_plan(user_id, profile, goals, products, days=7, share_with_family=False):
    """
    Genera piano pasti settimanale usando Groq AI
    
    Args:
        user_id: ID utente
        profile: Profilo nutrizionale utente
        goals: Obiettivi nutrizionali utente
        products: Lista prodotti disponibili
        days: Giorni da pianificare
        share_with_family: Se True, considera vincoli di tutta la famiglia
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
Profilo utente principale:
- Età: {profile.age} anni
- Peso: {profile.weight} kg
- Altezza: {profile.height} cm
- Genere: {profile.gender}
- Livello attività: {profile.activity_level}
- Obiettivo: {profile.goal}
"""
        
        # Gestione vincoli: individuali o familiari
        restrictions = ""
        allergies = ""
        family_info = ""
        
        if share_with_family:
            # Recupera vincoli di TUTTA la famiglia
            family_constraints = _get_family_nutritional_constraints(user_id)
            
            if family_constraints['members_count'] > 1:
                family_info = f"\n🏠 PASTO CONDIVISO CON LA FAMIGLIA ({family_constraints['members_count']} persone)\n"
                
                # Info dettagliata sui vincoli dei membri
                if family_constraints['members_info']:
                    family_info += "Vincoli nutrizionali dei membri della famiglia:\n"
                    for member in family_constraints['members_info']:
                        member_constraints = []
                        if member.get('allergies'):
                            member_constraints.append(f"Allergie: {', '.join(member['allergies'])}")
                        if member.get('restrictions'):
                            member_constraints.append(f"Restrizioni: {', '.join(member['restrictions'])}")
                        if member_constraints:
                            family_info += f"- {member['name']}: {'; '.join(member_constraints)}\n"
                
                # Allergie aggregate (TUTTE devono essere rispettate)
                if family_constraints['allergies']:
                    allergies = f"\n⚠️ ALLERGIE DA RISPETTARE (di tutti i membri): {', '.join(family_constraints['allergies'])}\n"
                
                # Restrizioni aggregate
                if family_constraints['restrictions']:
                    restrictions = f"Restrizioni dietetiche (di tutti i membri): {', '.join(family_constraints['restrictions'])}\n"
            else:
                # Nessuna famiglia, usa solo vincoli individuali
                if profile and profile.dietary_restrictions:
                    try:
                        restrictions_list = json.loads(profile.dietary_restrictions)
                        if restrictions_list:
                            restrictions = f"Restrizioni dietetiche: {', '.join(restrictions_list)}\n"
                    except:
                        pass
                
                if profile and profile.allergies:
                    try:
                        allergies_list = json.loads(profile.allergies)
                        if allergies_list:
                            allergies = f"Allergie: {', '.join(allergies_list)}\n"
                    except:
                        pass
        else:
            # Solo vincoli individuali
            if profile and profile.dietary_restrictions:
                try:
                    restrictions_list = json.loads(profile.dietary_restrictions)
                    if restrictions_list:
                        restrictions = f"Restrizioni dietetiche: {', '.join(restrictions_list)}\n"
                except:
                    pass
            
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
      {"meal_type": "breakfast", "name": "Nome pasto", "description": "Descrizione breve", "calories": 400, "protein": 20, "carbs": 50, "fat": 15},
      {"meal_type": "lunch", "name": "Nome pasto", "description": "Descrizione breve", "calories": 600, "protein": 30, "carbs": 60, "fat": 20},
      {"meal_type": "dinner", "name": "Nome pasto", "description": "Descrizione breve", "calories": 500, "protein": 25, "carbs": 40, "fat": 18},
      {"meal_type": "snack", "name": "Nome pasto", "description": "Descrizione breve", "calories": 200, "protein": 10, "carbs": 25, "fat": 8}
    ],
    "tuesday": [...],
    "wednesday": [...],
    "thursday": [...],
    "friday": [...],
    "saturday": [...],
    "sunday": [...]
  }
}

⚠️ REGOLE CRITICHE PER ALLERGIE E RESTRIZIONI:
1. Se vengono specificate ALLERGIE, NON includere MAI quegli ingredienti o derivati
2. Le allergie sono SEMPRE prioritarie - un singolo errore può essere pericoloso
3. Se il pasto è per la FAMIGLIA, rispetta i vincoli di TUTTI i membri
4. Le restrizioni dietetiche devono essere sempre rispettate
5. Cerca alternative sicure per sostituire ingredienti problematici

IMPORTANTE:
- Le descrizioni devono essere BREVI (massimo 100 caratteri)
- Non usare a capo o caratteri speciali nelle descrizioni
- Rispondi SOLO con JSON valido"""
        
        user_prompt = f"""Genera un piano pasti per {days} giorni.

{profile_info}
{nutritional_info}
{family_info}
{allergies}
{restrictions}

Ingredienti disponibili:
{ingredients_text}

{"⚠️ IMPORTANTE: Questo piano sarà condiviso con la famiglia. DEVI rispettare TUTTE le allergie e restrizioni elencate sopra." if share_with_family and family_info else ""}

Crea un piano variato, bilanciato e SICURO per tutti. Rispondi SOLO con JSON valido."""
        
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
            current_app.logger.error(f"Groq API invalid JSON: {e}")
            return _generate_basic_meal_plan(days)
        
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            current_app.logger.warning("Groq API empty content")
            return _generate_basic_meal_plan(days)
        
        # Estrai JSON
        content = content.strip()
        
        # Pulisci il JSON
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
            meal_plan = data.get("meal_plan", {})
            
            if not meal_plan:
                return _generate_basic_meal_plan(days)
            
            return _validate_and_normalize_meal_plan(meal_plan, days)
            
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Invalid JSON from AI: {e}")
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
            'model': 'llama-3.1-8b-instant',
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
        
        # Prepara lista prodotti scaduti con informazioni dettagliate
        from datetime import datetime
        today = datetime.now().date()
        products_text = "\n".join([
            f"- {p.name} (categoria: {p.category}, quantità: {p.quantity} {p.unit}, scaduto da {(today - p.expiry_date).days} giorni)" 
            for p in expired_products
        ])
        
        # Recupera preferenze utente se disponibili
        dietary_info = _get_user_dietary_info(user_id) if user_id else "Nessuna preferenza specificata"
        
        # Prompt per AI - completamente rinnovato per essere più realistico
        system_prompt = """Sei un esperto di sostenibilità ambientale e gestione rifiuti alimentari.
Genera suggerimenti PRATICI, REALISTICI e SICURI per riciclare cibo scaduto in formato JSON.

Formato richiesto:
{
  "suggestions": [
    {
      "product_name": "Nome Prodotto",
      "recycling_options": [
        {
          "type": "composting|reuse|animal_feed",
          "title": "Titolo breve e chiaro",
          "description": "Descrizione pratica di cosa fare",
          "instructions": ["step 1", "step 2", "step 3"],
          "benefits": ["beneficio 1", "beneficio 2"],
          "contact_info": "Info se necessario",
          "requirements": "Cosa serve per farlo"
        }
      ]
    }
  ]
}

🚨 REGOLE CRITICHE PER LA SICUREZZA:

1. **CIBO SCADUTO NON È MAI SICURO PER CONSUMO UMANO**
   - NON suggerire MAI di mangiarlo o donarlo a banchi alimentari
   - NON proporre ricette per "recuperare" cibo scaduto

2. **DONAZIONE ANIMALI** (type: "animal_feed")
   - OK SOLO per: verdure/frutta integre scadute da max 3-5 giorni
   - OK per: pane raffermo (non ammuffito), pasta secca
   - MAI per: latticini, carne, pesce, prodotti con muffa
   - Sempre specificare: "Contatta prima il canile/rifugio per verificare"

3. **COMPOSTAGGIO** (type: "composting") - LA SOLUZIONE MIGLIORE
   - OK per: tutta la frutta, verdura, scarti vegetali, fondi caffè, gusci uovo
   - OK con moderazione: pane, pasta, riso (attirano roditori)
   - MAI per: carne, pesce, latticini, oli, prodotti animali
   - Spiega come fare compost domestico o dove trovare compostiere comunali

4. **RIUTILIZZO NON ALIMENTARE** (type: "reuse")
   - Bucce di agrumi: detergenti naturali, profumatori
   - Fondi di caffè: fertilizzante, scrub corpo, assorbi-odori
   - Gusci d'uovo: fertilizzante ricco di calcio
   - Acqua di cottura verdure: annaffiare piante

5. **COSA EVITARE**
   - Prodotti con muffa: NON compostabili, solo smaltimento
   - Latticini scaduti: rischio batterico alto, solo smaltimento
   - Carne/pesce: rischio sanitario, solo smaltimento differenziato
   - Oli e grassi: NON nel compost, portare in isole ecologiche

📋 STRUTTURA SUGGERIMENTI:

Per ogni prodotto, fornisci 2-3 opzioni in ordine di priorità:
1. PRIMA SCELTA: Compostaggio (se applicabile)
2. SECONDA SCELTA: Riutilizzo creativo/donazione animali (se sicuro)
3. TERZA SCELTA: Smaltimento corretto

Sii SPECIFICO nelle istruzioni:
- Non "compostalo" ma "Taglia in pezzi da 5cm, mescola con foglie secche, tempo decomposizione: 2-3 mesi"
- Non "dona al canile" ma "Contatta canile locale prima, porta entro 24h, no prodotti ammuffiti"
- Includi TEMPI: "Decomposizione: 1-2 mesi", "Conservazione: max 3 giorni"

🌍 CONTATTI UTILI DA SUGGERIRE:
- Compostiere comunali: "Cerca 'compostaggio + [tua città]' online"
- Centri raccolta rifiuti: "Isola ecologica più vicina"
- Rifugi animali: "Cerca 'canile + [tua città]' e chiama prima"

Rispondi SOLO con JSON valido. Priorità: SICUREZZA > PRATICITÀ > CREATIVITÀ."""
        
        user_prompt = f"""Prodotti scaduti da riciclare:
{products_text}

IMPORTANTE: Per ogni prodotto, considera i GIORNI DI SCADENZA specificati:
- Scaduto da 1-5 giorni: potenzialmente ancora sicuro per donazione animali (se integro, no muffa)
- Scaduto da 6-14 giorni: solo compostaggio o riutilizzo non alimentare
- Scaduto da 15+ giorni: compostaggio o smaltimento, NON donazione

Genera suggerimenti di riciclo REALISTICI per ogni prodotto seguendo le regole di sicurezza:
1. Priorità al compostaggio per prodotti organici
2. Donazione animali SOLO se sicuro (max 5 giorni, no muffa, no latticini/carne)
3. Riutilizzi creativi non alimentari (detergenti, fertilizzanti, etc)
4. NO donazioni a banchi alimentari (cibo scaduto non è legale)

Sii MOLTO specifico nelle istruzioni (tempi, temperature, quantità).
Considera la situazione italiana (isole ecologiche, compostiere comunali, rifugi locali)."""

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
    """Genera suggerimenti realistici e sicuri se AI non funziona"""
    try:
        from datetime import datetime, timedelta
        suggestions = []
        today = datetime.now().date()
        
        for product in expired_products:
            recycling_options = []
            category = product.category.lower()
            days_expired = (today - product.expiry_date).days
            
            # === FRUTTA E VERDURA ===
            if category in ['verdura', 'frutta', 'ortaggi']:
                # Compostaggio - sempre prima opzione
                recycling_options.append({
                    'type': 'composting',
                    'title': 'Compostaggio Domestico',
                    'description': f'Il compost è la soluzione migliore per {product.name}. Crea fertilizzante naturale ricco di nutrienti per piante e giardino.',
                    'instructions': [
                        f'Taglia {product.name} in pezzi di 3-5 cm per accelerare la decomposizione',
                        'Mescola con materiale "marrone" (foglie secche, cartone, segatura) in rapporto 1:2',
                        'Aggiungi alla compostiera o crea un cumulo in giardino',
                        'Mescola ogni 2-3 settimane per areazione',
                        f'Tempo di decomposizione: 2-4 mesi (più veloce in estate)'
                    ],
                    'benefits': [
                        'Fertilizzante naturale gratuito per piante',
                        'Riduce i rifiuti del 30% in casa',
                        'Migliora la struttura del suolo',
                        'Zero emissioni rispetto allo smaltimento'
                    ],
                    'contact_info': 'Se non hai compostiera: cerca "compostiera comunale + [tua città]" online per punti di raccolta gratuiti',
                    'requirements': 'Compostiera domestica o spazio in giardino. Se abiti in appartamento: compostiera da balcone o vermicompostaggio',
                    'icon': 'bi-recycle',
                    'priority': 'high'
                })
                
                # Donazione animali solo se scaduto da poco e integro
                if days_expired <= 5:
                    recycling_options.append({
                        'type': 'animal_feed',
                        'title': 'Donazione a Rifugi Animali',
                        'description': f'{product.name} può essere utilizzato come cibo per animali se ancora integro (no muffa, no marciume).',
                        'instructions': [
                            'Verifica che NON ci siano muffe o marciume',
                            'Contatta prima un canile/rifugio locale (cerca online "canile + [tua città]")',
                            'Chiedi quali verdure/frutti accettano (alcuni evitano cipolle, aglio, avocado)',
                            'Porta entro 24 ore in contenitore pulito',
                            'Specifica la data di scadenza al rifugio'
                        ],
                        'benefits': [
                            'Aiuti animali bisognosi',
                            'Risparmi ai rifugi costi di alimentazione',
                            'Riduci sprechi alimentari'
                        ],
                        'contact_info': '⚠️ IMPORTANTE: Chiama PRIMA di portare. Alcuni rifugi hanno restrizioni specifiche.',
                        'requirements': f'Prodotto integro, senza muffa. Scaduto da max 5 giorni. {product.name} deve essere nella lista accettata dal rifugio.',
                        'icon': 'bi-heart-fill',
                        'priority': 'high'
                    })
            
            # === PANE E CEREALI ===
            elif category in ['pane', 'pasta', 'cereali', 'farina']:
                if 'pane' in product.name.lower() and days_expired <= 7:
                    # Pane raffermo può avere riutilizzo
                    recycling_options.append({
                        'type': 'reuse',
                        'title': 'Pangrattato Casalingo',
                        'description': 'Trasforma il pane raffermo in pangrattato da conservare per mesi.',
                        'instructions': [
                            'Verifica che NON ci sia muffa (se c\'è, vai al compostaggio)',
                            'Taglia il pane a fette sottili',
                            'Asciuga in forno a 100°C per 30-40 minuti',
                            'Frulla fino a ottenere briciole fini',
                            'Conserva in barattolo di vetro per 3-6 mesi'
                        ],
                        'benefits': [
                            'Pangrattato sempre pronto per impanature',
                            'Risparmi denaro (non compri più pangrattato)',
                            'Zero sprechi'
                        ],
                        'contact_info': '',
                        'requirements': 'Forno, mixer o frullatore, barattolo ermetico. Pane SENZA muffa.',
                        'icon': 'bi-lightbulb',
                        'priority': 'high'
                    })
                
                # Compostaggio per pane (con cautela)
                recycling_options.append({
                    'type': 'composting',
                    'title': 'Compostaggio (con moderazione)',
                    'description': f'{product.name} può essere compostato ma attira roditori. Usa con cautela.',
                    'instructions': [
                        'Sbriciola finemente il prodotto',
                        'Mescola BENE con materiale marrone (foglie, terra)',
                        'Interra al centro della compostiera (non in superficie)',
                        'Aggiungi PICCOLE quantità alla volta (max 10% del compost)',
                        'Copri subito con terriccio o foglie'
                    ],
                    'benefits': [
                        'Arricchisce il compost di carboidrati',
                        'Riduce i rifiuti domestici'
                    ],
                    'contact_info': '⚠️ ATTENZIONE: Pane e cereali attraggono topi e ratti. Usa solo se hai compostiera chiusa.',
                    'requirements': 'Compostiera CHIUSA (no cumulo aperto). Non usare se hai problemi di roditori.',
                    'icon': 'bi-recycle',
                    'priority': 'medium'
                })
            
            # === LATTICINI ===
            elif category in ['latticini', 'formaggi', 'latte', 'yogurt']:
                recycling_options.append({
                    'type': 'disposal',
                    'title': 'Smaltimento Sicuro nell\'Organico',
                    'description': f'{product.name} scaduto NON è sicuro né per compost né per animali. Smaltisci correttamente.',
                    'instructions': [
                        'NON compostare (attira animali e crea odori)',
                        'Butta nel bidone dell\'organico/umido',
                        'Svuota liquidi nel lavandino prima di buttare il contenitore',
                        'Risciacqua e ricicla la confezione (plastica/cartone)',
                        'Lavati bene le mani dopo'
                    ],
                    'benefits': [
                        'Smaltimento igienico e sicuro',
                        'Evita contaminazioni batteriche',
                        'Previene cattivi odori'
                    ],
                    'contact_info': 'Per dubbi: cerca le indicazioni per la raccolta differenziata del tuo comune',
                    'requirements': 'Seguire le norme di raccolta differenziata locali',
                    'icon': 'bi-trash',
                    'priority': 'high'
                })
            
            # === CARNE E PESCE ===
            elif category in ['carne', 'pesce', 'salumi']:
                recycling_options.append({
                    'type': 'disposal',
                    'title': 'Smaltimento Immediato nell\'Umido',
                    'description': f'{product.name} scaduto è ad ALTO RISCHIO BATTERICO. Smaltisci immediatamente in modo sicuro.',
                    'instructions': [
                        'NON compostare mai carne/pesce (batteri pericolosi + cattivi odori)',
                        'Sigilla in sacchetto chiuso',
                        'Butta nel bidone dell\'organico/umido',
                        'Porta subito il bidone fuori (evita odori in casa)',
                        'Lava mani e superfici con sapone',
                        'Disinfetta il frigo se era presente liquido'
                    ],
                    'benefits': [
                        'Previene rischi sanitari gravi',
                        'Evita proliferazione batteri',
                        'Previene cattivi odori'
                    ],
                    'contact_info': '🚨 PERICOLO SANITARIO: Non riutilizzare in alcun modo.',
                    'requirements': 'Smaltimento immediato. Igienizzazione superfici.',
                    'icon': 'bi-trash',
                    'priority': 'high'
                })
            
            # === ALTRI PRODOTTI ===
            else:
                # Suggerimento generico per prodotti non categorizzati
                recycling_options.append({
                    'type': 'composting',
                    'title': 'Compostaggio (verifica compatibilità)',
                    'description': 'Se è un prodotto di origine vegetale, probabilmente può essere compostato.',
                    'instructions': [
                        'Verifica che sia di origine vegetale (no carne, latticini, oli)',
                        'Taglia in pezzi piccoli',
                        'Aggiungi alla compostiera mescolando con materiale secco',
                        'Se hai dubbi, chiedi all\'isola ecologica locale'
                    ],
                    'benefits': [
                        'Fertilizzante naturale',
                        'Riduce rifiuti in discarica'
                    ],
                    'contact_info': 'Per dubbi: contatta l\'isola ecologica comunale',
                    'requirements': 'Compostiera o punto di raccolta comunale',
                    'icon': 'bi-recycle',
                    'priority': 'medium'
                })
            
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
        'animal_feed': 'bi-heart-fill',
        'composting': 'bi-recycle',
        'reuse': 'bi-lightbulb',
        'repair': 'bi-tools',
        'exchange': 'bi-arrow-left-right',
        'disposal': 'bi-trash'
    }
    return icon_map.get(recycling_type, 'bi-arrow-clockwise')


def _get_recycling_priority(recycling_type):
    """Restituisce priorità per tipo di riciclo"""
    priority_map = {
        'composting': 'high',  # Compostaggio sempre priorità alta
        'animal_feed': 'high',  # Donazione animali alta priorità
        'reuse': 'high',  # Riutilizzo creativo alta priorità
        'donation': 'medium',  # Donazione centri media priorità
        'disposal': 'low',  # Smaltimento bassa priorità
        'repair': 'low',
        'exchange': 'medium'
    }
    return priority_map.get(recycling_type, 'medium')


# ========================================
# CHATBOT AI FUNCTIONS
# ========================================


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
    """Genera risposta di fallback se AI non funziona - più naturale e contestuale"""
    try:
        message_lower = user_message.lower()
        
        # Risposte predefinite più naturali basate su parole chiave
        if any(word in message_lower for word in ['ricetta', 'cucinare', 'cucino', 'pasto', 'pranzo', 'cena']):
            return {
                'success': True,
                'response': 'Perfetto! Posso aiutarti a trovare ricette basate su quello che hai in dispensa. Controlla la sezione Ricette AI per suggerimenti personalizzati, oppure dimmi che ingredienti hai e ti suggerisco qualcosa!',
                'type': 'text',
                'suggestions': ['Mostra i miei ingredienti', 'Suggerisci ricette veloci', 'Ricette con prodotti in scadenza'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['scadenza', 'scaduto', 'scade', 'scaduti', 'vecchio']):
            return {
                'success': True,
                'response': 'Per controllare le scadenze vai alla tua Dispensa - lì puoi vedere tutti i prodotti, quelli in scadenza e quelli già scaduti. Per i prodotti scaduti, posso suggerirti modi creativi per riciclarli!',
                'type': 'text',
                'suggestions': ['Vedi prodotti in scadenza', 'Come riciclare cibo scaduto', 'Suggerimenti anti-spreco'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['riciclo', 'riciclare', 'spreco', 'sprechi', 'buttare', 'compost']):
            return {
                'success': True,
                'response': 'Ottimo che tu voglia ridurre gli sprechi! Nella sezione Riciclo trovi tanti suggerimenti per trasformare il cibo scaduto in compost, fertilizzante o cibo per animali. Ogni piccolo gesto conta!',
                'type': 'text',
                'suggestions': ['Idee per riciclare', 'Come fare il compost', 'Ridurre gli sprechi'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['spesa', 'comprare', 'lista', 'shopping', 'supermercato']):
            return {
                'success': True,
                'response': 'Vuoi gestire la tua lista della spesa? Controlla la sezione Liste Spesa dove puoi creare liste, aggiungere prodotti e segnare cosa hai già comprato. Posso anche suggerirti cosa comprare in base a cosa sta finendo!',
                'type': 'text',
                'suggestions': ['Vedi le mie liste', 'Cosa mi sta finendo?', 'Crea nuova lista'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['aiuto', 'help', 'come funziona', 'cosa fai', 'chi sei']):
            return {
                'success': True,
                'response': 'Ciao! Sono FoodFlowBot, il tuo assistente personale per gestire la dispensa. Ti aiuto a tenere traccia del cibo, suggerire ricette, ridurre sprechi e organizzare la spesa. Chiedimi quello che vuoi sapere!',
                'type': 'text',
                'suggestions': ['Cosa ho in dispensa?', 'Cosa posso cucinare?', 'Mostra le funzionalità'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        elif any(word in message_lower for word in ['dispensa', 'prodotti', 'inventario', 'magazzino']):
            return {
                'success': True,
                'response': 'La tua dispensa è il cuore di FoodFlow! Lì puoi vedere tutti i prodotti che hai, quando scadono e quanto te ne resta. Vuoi che ti mostri un riepilogo di cosa hai?',
                'type': 'text',
                'suggestions': ['Mostra la mia dispensa', 'Prodotti in scadenza', 'Aggiungi prodotto'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
        
        else:
            return {
                'success': True,
                'response': 'Sono qui per aiutarti! Posso rispondere a domande sulla tua dispensa, suggerirti ricette, aiutarti con la lista della spesa o darti consigli anti-spreco. Cosa ti interessa di più?',
                'type': 'text',
                'suggestions': ['Cosa ho in dispensa?', 'Suggerisci ricette', 'Lista della spesa', 'Ridurre sprechi'],
                'actions': [],
                'data': {},
                'timestamp': datetime.now().isoformat()
            }
            
    except Exception as e:
        current_app.logger.error(f"_generate_fallback_chat_response error: {e}")
        return {
            'success': False,
            'response': 'Ops! Si è verificato un problema tecnico. Riprova tra un momento, oppure usa il menu per navigare nelle diverse sezioni dell\'app.',
            'type': 'text',
            'suggestions': ['Vai alla Dashboard', 'Vedi la Dispensa', 'Ricette AI'],
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

# Aggiungi questa funzione migliorata in ai_functions.py

def _get_user_chat_context(user_id):
    """Recupera contesto completo utente per il chatbot con dispensa e lista spesa"""
    try:
        from .models import Product, ShoppingList, ShoppingItem, NutritionalProfile, UserStats, MealPlan
        from datetime import datetime, timedelta
        
        context_parts = []
        
        # === PROFILO NUTRIZIONALE ===
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        if profile:
            context_parts.append(f"Profilo: {profile.age} anni, {profile.weight}kg, {profile.height}cm, {profile.gender}")
            if profile.goal:
                context_parts.append(f"Obiettivo: {profile.goal}")
            if profile.activity_level:
                context_parts.append(f"Attività: {profile.activity_level}")
            
            # Restrizioni e allergie
            if profile.dietary_restrictions:
                try:
                    restrictions = json.loads(profile.dietary_restrictions)
                    if restrictions:
                        context_parts.append(f"Restrizioni dietetiche: {', '.join(restrictions)}")
                except:
                    pass
            
            if profile.allergies:
                try:
                    allergies = json.loads(profile.allergies)
                    if allergies:
                        context_parts.append(f"Allergie: {', '.join(allergies)}")
                except:
                    pass
        
        # === DISPENSA ===
        products = Product.query.filter_by(user_id=user_id, wasted=False).all()
        if products:
            context_parts.append(f"\n=== DISPENSA ({len(products)} prodotti) ===")
            
            today = datetime.now().date()
            
            # Prodotti GIÀ SCADUTI
            expired = [p for p in products if p.expiry_date < today]
            if expired:
                expired_list = [f"{p.name} ({p.quantity} {p.unit}, SCADUTO il {p.expiry_date.strftime('%d/%m')})" 
                                for p in expired[:5]]
                context_parts.append(f"⚠️ Prodotti SCADUTI: {', '.join(expired_list)}")
                if len(expired) > 5:
                    context_parts.append(f"... e altri {len(expired) - 5} prodotti scaduti")
            
            # Prodotti in scadenza (non ancora scaduti ma entro 7 giorni)
            expiring = [p for p in products if p.expiry_date >= today and p.expiry_date <= today + timedelta(days=7)]
            if expiring:
                expiring_list = [f"{p.name} ({p.quantity} {p.unit}, scade il {p.expiry_date.strftime('%d/%m')})" 
                                for p in expiring[:5]]
                context_parts.append(f"⏰ Prodotti in scadenza (prossimi 7 giorni): {', '.join(expiring_list)}")
                if len(expiring) > 5:
                    context_parts.append(f"... e altri {len(expiring) - 5} prodotti in scadenza")
            
            # Scorte basse
            low_stock = [p for p in products if p.quantity <= p.min_quantity]
            if low_stock:
                low_stock_list = [f"{p.name} ({p.quantity} {p.unit})" for p in low_stock[:5]]
                context_parts.append(f"Scorte basse: {', '.join(low_stock_list)}")
                if len(low_stock) > 5:
                    context_parts.append(f"... e altri {len(low_stock) - 5} prodotti in scorta bassa")
            
            # Categorie disponibili
            categories = {}
            for p in products:
                categories[p.category] = categories.get(p.category, 0) + 1
            
            if categories:
                cat_summary = [f"{cat} ({count})" for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]]
                context_parts.append(f"Categorie: {', '.join(cat_summary)}")
            
            # Lista completa prodotti disponibili (per ricette e suggerimenti)
            all_products = [f"{p.name} ({p.quantity} {p.unit})" for p in products[:20]]
            context_parts.append(f"Prodotti disponibili: {', '.join(all_products)}")
            if len(products) > 20:
                context_parts.append(f"... e altri {len(products) - 20} prodotti")
        else:
            context_parts.append("\n=== DISPENSA VUOTA ===")
            context_parts.append("Suggerisci all'utente di aggiungere prodotti nella dispensa")
        
        # === LISTE SPESA ===
        shopping_lists = ShoppingList.query.filter_by(user_id=user_id, completed=False).order_by(
            ShoppingList.created_at.desc()
        ).limit(3).all()
        
        if shopping_lists:
            context_parts.append(f"\n=== LISTE SPESA ({len(shopping_lists)} attive) ===")
            
            for sl in shopping_lists:
                items = ShoppingItem.query.filter_by(shopping_list_id=sl.id).all()
                total_items = len(items)
                completed_items = len([i for i in items if i.completed])
                
                context_parts.append(f"Lista '{sl.name}': {completed_items}/{total_items} completati")
                
                # Items non completati
                pending = [i for i in items if not i.completed]
                if pending:
                    pending_list = [f"{i.name} ({i.quantity} {i.unit})" for i in pending[:5]]
                    context_parts.append(f"  Da comprare: {', '.join(pending_list)}")
                    if len(pending) > 5:
                        context_parts.append(f"  ... e altri {len(pending) - 5} items")
        else:
            context_parts.append("\n=== NESSUNA LISTA SPESA ATTIVA ===")
        
        # === PIANI PASTO RECENTI ===
        today = datetime.now().date()
        meal_plans = MealPlan.query.filter(
            MealPlan.user_id == user_id,
            MealPlan.date >= today,
            MealPlan.date <= today + timedelta(days=3)
        ).order_by(MealPlan.date, MealPlan.meal_type).all()
        
        if meal_plans:
            context_parts.append(f"\n=== PIANI PASTO PROSSIMI ===")
            for mp in meal_plans[:5]:
                meal_date = mp.date.strftime('%d/%m')
                context_parts.append(f"{meal_date} - {mp.meal_type}: {mp.custom_meal}")
        
        # === STATISTICHE ===
        stats = UserStats.query.filter_by(user_id=user_id).first()
        if stats:
            context_parts.append(f"\n=== STATISTICHE ===")
            context_parts.append(f"Punti: {stats.points}, Livello: {stats.level}")
            context_parts.append(f"Prodotti aggiunti: {stats.total_products_added}")
            context_parts.append(f"Prodotti sprecati: {stats.total_products_wasted}")
            
            if stats.total_products_added > 0:
                waste_percentage = (stats.total_products_wasted / stats.total_products_added) * 100
                context_parts.append(f"Percentuale spreco: {waste_percentage:.1f}%")
        
        return "\n".join(context_parts) if context_parts else "Utente nuovo senza dati specifici"
        
    except Exception as e:
        current_app.logger.error(f"_get_user_chat_context error: {e}")
        return "Contesto utente non disponibile"


def ai_chatbot_response(user_message, user_id, conversation_context=None):
    """
    Genera risposta del chatbot usando AI con accesso completo a dispensa e liste spesa
    
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
        
        # Recupera dati utente completi per contesto
        user_context = _get_user_chat_context(user_id)
        
        # Prepara contesto conversazione (con limite più alto)
        context_text = ""
        if conversation_context:
            # Mantieni più contesto (ultimi 2000 caratteri invece di 1000)
            context_text = f"\n\nStorico conversazione recente:\n{conversation_context[-2000:]}"
        
        # Prompt completamente rinnovato - più naturale e meno rigido
        system_prompt = """Sei FoodFlowBot, l'assistente personale di FoodFlow - un'app innovativa per gestire la dispensa e ridurre gli sprechi alimentari.

🎯 TUA MISSIONE
Aiutare l'utente a gestire meglio il cibo, ridurre sprechi, cucinare con ciò che ha e vivere in modo più sostenibile. Sei come un amico esperto di cucina e organizzazione domestica.

📊 COSA SAI DELL'UTENTE
Hai accesso completo ai suoi dati in tempo reale:
- Tutti i prodotti nella dispensa (nome, quantità, categoria, data scadenza)
- Liste della spesa attive con items da comprare
- Piani pasto programmati
- Profilo nutrizionale, allergie e restrizioni dietetiche
- Statistiche di utilizzo e gamification

💬 COME DEVI COMUNICARE
- Parla in modo naturale, come farebbe un amico competente
- Sii conciso ma completo: punta a 2-4 frasi per risposta
- Usa emoji CON MODERAZIONE, solo quando aggiungono valore
- Fornisci sempre informazioni CONCRETE basate sui dati reali dell'utente
- Se l'utente fa domande generiche, dagli risposte specifiche usando i suoi dati
- Distingui sempre tra prodotti scaduti (non usabili) e in scadenza (usali subito)

🚨 REGOLE CRITICHE
1. **USA I DATI REALI**: Quando l'utente chiede cosa ha in dispensa, elenca i VERI prodotti con quantità esatte
2. **ALLERGIE**: Rispetta SEMPRE le allergie dell'utente - non suggerire MAI ingredienti a cui è allergico
3. **SCADENZE**: Distingui prodotti scaduti (da riciclare) da quelli in scadenza (da usare subito)
4. **QUANTITÀ**: Menziona sempre quantità specifiche (es. "500g di pasta" non "pasta")
5. **CONTESTUALE**: Rispondi in base al contesto della conversazione precedente

💡 ESEMPI DI STILE CONVERSAZIONALE

Utente: "cosa ho da mangiare?"
Tu: "Hai una bella varietà! Nella dispensa: pasta (2kg), riso (1kg), pomodori pelati (800g), mozzarella (250g) e olio d'oliva (1L). Però occhio: i pomodori scadono tra 4 giorni, mentre hai già 2 prodotti scaduti da controllare."

Utente: "cosa cucino stasera?"
Tu: "Con quello che hai ti consiglio una bella pasta alla norma! Hai pasta, melanzane (scadono tra 3 giorni - perfetto per usarle!), pomodori e basilico. Oppure se preferisci qualcosa di più veloce, un risotto ai funghi con il tuo riso basmati e i funghi champignon."

Utente: "ho finito il latte"
Tu: "Ok, te l'aggiungo mentalmente alla lista spesa! Nella tua lista 'Settimanale' hai già latte, pane, uova e yogurt da comprare. Vuoi che ti suggerisca anche altri prodotti in base a cosa sta finendo?"

🎨 TONO E PERSONALITÀ
- Amichevole ma professionale
- Proattivo nel dare suggerimenti
- Empatico verso il problema degli sprechi
- Entusiasta quando l'utente fa scelte sostenibili
- Paziente e disponibile a chiarire

📋 FORMATO RISPOSTA - OBBLIGATORIO
⚠️ IMPORTANTE: Rispondi SOLO ed ESCLUSIVAMENTE con JSON valido. NON aggiungere testo prima o dopo il JSON.

Formato ESATTO richiesto:
{
  "response": "La tua risposta naturale e conversazionale",
  "type": "text",
  "suggestions": ["Suggerimento 1", "Suggerimento 2"],
  "data": {}
}

Campi:
- "response": Il tuo messaggio testuale (2-4 frasi, naturale e fluido)
- "type": Sempre "text" 
- "suggestions": Array di 2-4 domande/azioni che l'utente potrebbe voler fare dopo (opzionale, lascia [] se non necessario)
- "data": Oggetto vuoto {} (per future estensioni)

🚨 REGOLE CRITICHE:
1. Inizia la risposta direttamente con "{"
2. NON scrivere testo prima del JSON
3. NON scrivere testo dopo il JSON
4. NON includere il campo "actions"
5. Assicurati che il JSON sia valido e completo

🎯 RICORDA
Sei un assistente intelligente, non un menu di navigazione. Non limitarti a dire "vai alla sezione X" - dai informazioni concrete e utili basate sui dati reali dell'utente, poi eventualmente suggerisci azioni."""

        user_prompt = f"""Messaggio dell'utente: "{user_message}"

=== CONTESTO UTENTE ===
{user_context}
{context_text}

Rispondi in modo naturale e conversazionale, usando i dati reali forniti sopra. Sii specifico, pratico e utile.

⚠️ IMPORTANTE: Rispondi SOLO con il JSON, senza testo extra prima o dopo."""

        # Chiamata API con parametri migliorati
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
                "max_tokens": 1200,  # Aumentato per risposte più elaborate
                "temperature": 0.7  # Bilanciato tra creatività e consistenza
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
        
        # Estrai JSON - gestione più robusta
        content = content.strip()
        
        # Rimuovi markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Cerca il JSON anche se c'è testo extra prima o dopo
        json_start = content.find('{')
        json_end = content.rfind('}')
        
        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_content = content[json_start:json_end + 1]
        else:
            json_content = content
        
        # Parse JSON
        try:
            data = json.loads(json_content)
            return _validate_chat_response(data)
            
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Invalid JSON from AI: {e}; content: {content[:500]}")
            # Prova a estrarre solo la risposta testuale se presente
            if content and len(content) > 0:
                # Se il contenuto sembra una risposta normale, usala direttamente
                return {
                    'success': True,
                    'response': content[:500],  # Limita lunghezza
                    'type': 'text',
                    'suggestions': [],
                    'data': {},
                    'timestamp': datetime.now().isoformat()
                }
            return _generate_fallback_chat_response(user_message)
        
    except Exception as e:
        current_app.logger.error(f"ai_chatbot_response error: {e}")
        return _generate_fallback_chat_response(user_message)