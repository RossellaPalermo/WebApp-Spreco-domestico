"""
AI Functions - FoodFlow
Funzioni basate su AI/LLM per suggerimenti intelligenti
"""

import os
import json
import requests
from datetime import datetime, timedelta
from flask import current_app

from .models import Product, NutritionalProfile, MealPlan

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
    Genera piano pasti settimanale ottimizzato
    
    Args:
        user_id: ID utente
        days: Giorni da pianificare
    
    Returns:
        dict: Piano pasti per giorni {day: [meals]}
    """
    try:
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            return _generate_basic_meal_plan(days)
        
        # TODO: Implementare con Groq AI
        # Per ora ritorna piano base
        return _generate_basic_meal_plan(days)
        
    except Exception as e:
        current_app.logger.error(f"ai_optimize_meal_planning error: {e}")
        return {}


def _generate_basic_meal_plan(days=7):
    """Genera piano pasti base (fallback)"""
    days_map = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    
    meal_templates = {
        'breakfast': ['Omelette', 'Porridge', 'Pancakes', 'Yogurt con frutta'],
        'lunch': ['Insalata di pollo', 'Pasta integrale', 'Riso con verdure', 'Zuppa di legumi'],
        'dinner': ['Pesce al forno', 'Pollo alla griglia', 'Burger vegetariano', 'Salmone']
    }
    
    plan = {}
    for i, day in enumerate(days_map[:days]):
        plan[day] = [
            meal_templates['breakfast'][i % len(meal_templates['breakfast'])],
            meal_templates['lunch'][i % len(meal_templates['lunch'])],
            meal_templates['dinner'][i % len(meal_templates['dinner'])]
        ]
    
    return plan


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