"""
Smart Functions - FoodFlow
Funzioni intelligenti per logica business
"""

from datetime import datetime, timedelta
from sqlalchemy import func
from . import db
from .models import (
    User, UserStats, Product, ShoppingList, ShoppingItem,
    NutritionalProfile, NutritionalGoal, MealPlan, RewardHistory
)
import json

# ========================================
# CONSTANTS
# ========================================

ACTIVITY_MULTIPLIERS = {
    'sedentary': 1.2,
    'light': 1.375,
    'moderate': 1.55,
    'active': 1.725,
    'very_active': 1.9
}

PRIORITY_LEVELS = {
    'low': 0,
    'medium': 1,
    'high': 2
}

POINTS_TABLE = {
    'product_added': 10,
    'shopping_list_created': 5,
    'shopping_completed': 20,
    'waste_reduction': 15,
    'achieve_nutrition_goal': 20,
    'create_recipe': 5,
    'first_product': 50,  # Badge milestone
}


# ========================================
# DISPENSA - PRODOTTI
# ========================================

def get_expiring_products(user_id, days=7):
    """
    Recupera prodotti in scadenza entro N giorni
    
    Args:
        user_id: ID utente
        days: Giorni di anticipo (default 7)
    
    Returns:
        Lista di Product objects
    """
    cutoff_date = datetime.now().date() + timedelta(days=days)
    
    return Product.query.filter(
        Product.user_id == user_id,
        Product.expiry_date <= cutoff_date,
        Product.wasted == False
    ).order_by(Product.expiry_date.asc()).all()


def get_low_stock_products(user_id, threshold_multiplier=1.0):
    """
    Recupera prodotti con scorte basse
    
    Args:
        user_id: ID utente
        threshold_multiplier: Moltiplicatore soglia (default 1.0 = min_quantity)
    
    Returns:
        Lista di Product objects
    """
    return Product.query.filter(
        Product.user_id == user_id,
        Product.quantity <= Product.min_quantity * threshold_multiplier,
        Product.wasted == False
    ).order_by(Product.quantity.asc()).all()


def get_products_by_category(user_id, category=None):
    """Raggruppa prodotti per categoria"""
    query = Product.query.filter_by(user_id=user_id, wasted=False)
    
    if category:
        return query.filter_by(category=category).all()
    
    # Raggruppa per categoria
    products = query.all()
    categories = {}
    
    for product in products:
        cat = product.category or 'Altro'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(product)
    
    return categories


# ========================================
# WASTE ANALYTICS
# ========================================

def calculate_waste_reduction_score(user_id, days=30):
    """
    Calcola score riduzione sprechi
    
    Returns:
        {
            'score': int (0-100),
            'grade': str ('A', 'B', 'C', 'D', 'F'),
            'percentage': float,
            'details': dict
        }
    """
    try:
        cutoff_date = datetime.now().date() - timedelta(days=days)
        
        # Query ottimizzata con aggregation
        stats = db.session.query(
            func.count(Product.id).label('total_products'),
            func.sum(Product.quantity).label('total_quantity'),
            func.count(Product.id).filter(Product.wasted == True).label('wasted_products'),
            func.sum(Product.quantity).filter(Product.wasted == True).label('wasted_quantity')
        ).filter(
            Product.user_id == user_id,
            Product.created_at >= cutoff_date
        ).first()
        
        total_products = stats.total_products or 0
        total_quantity = float(stats.total_quantity or 0)
        wasted_products = stats.wasted_products or 0
        wasted_quantity = float(stats.wasted_quantity or 0)
        
        if total_quantity == 0:
            return {
                'score': 100,
                'grade': 'A',
                'percentage': 100.0,
                'max_score': 100,
                'details': {
                    'total_products': total_products,
                    'wasted_products': wasted_products,
                    'total_quantity': total_quantity,
                    'wasted_quantity': wasted_quantity,
                    'waste_percentage': 0.0
                }
            }
        
        # Calcola percentuali
        waste_percentage = (wasted_quantity / total_quantity) * 100
        score = max(0, min(100, int(100 - waste_percentage)))
        
        # Determina grade
        if score >= 90:
            grade = 'A'
        elif score >= 80:
            grade = 'B'
        elif score >= 70:
            grade = 'C'
        elif score >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        return {
            'score': score,
            'grade': grade,
            'percentage': round(100 - waste_percentage, 1),
            'max_score': 100,
            'details': {
                'total_products': total_products,
                'wasted_products': wasted_products,
                'total_quantity': round(total_quantity, 2),
                'wasted_quantity': round(wasted_quantity, 2),
                'waste_percentage': round(waste_percentage, 1),
                'period_days': days
            }
        }
        
    except Exception as e:
        return {
            'score': 0,
            'grade': 'F',
            'percentage': 0.0,
            'max_score': 100,
            'details': {'error': str(e)}
        }


# ========================================
# SHOPPING LIST INTELLIGENTE
# ========================================

def generate_smart_shopping_list(user_id, days_ahead=7):
    """
    Genera lista spesa intelligente
    
    Analizza:
    - Prodotti in esaurimento
    - Prodotti in scadenza (da sostituire)
    - Ingredienti da meal plan
    - Pattern di acquisto
    
    Returns:
        {
            'success': bool,
            'items': list,
            'total_items': int,
            'by_priority': dict
        }
    """
    try:
        suggestions = {}
        
        # 1. Prodotti in esaurimento (priorità alta)
        low_stock = get_low_stock_products(user_id)
        for product in low_stock:
            key = product.name.lower()
            suggestions[key] = {
                'name': product.name,
                'quantity': product.min_quantity * 2,
                'unit': product.unit,
                'category': product.category,
                'priority': 'high',
                'source': 'low_stock',
                'reason': f'Scorte basse: {product.quantity} {product.unit} rimanenti'
            }
        
        # 2. Prodotti in scadenza imminente (da sostituire)
        expiring_soon = get_expiring_products(user_id, days=3)
        for product in expiring_soon:
            key = product.name.lower()
            if key not in suggestions:
                suggestions[key] = {
                    'name': product.name,
                    'quantity': product.quantity,
                    'unit': product.unit,
                    'category': product.category,
                    'priority': 'medium',
                    'source': 'expiring',
                    'reason': f'Scade il {product.expiry_date.strftime("%d/%m/%Y")}'
                }
        
        # 3. Ingredienti da meal plan prossimi giorni
        upcoming_meals = MealPlan.query.filter(
            MealPlan.user_id == user_id,
            MealPlan.date >= datetime.now().date(),
            MealPlan.date <= datetime.now().date() + timedelta(days=days_ahead)
        ).all()
        
        # (Qui andrebbe parsing ingredienti da ricette - da implementare)
        
        # Converti in lista e prioritizza
        items_list = list(suggestions.values())
        items_list.sort(key=lambda x: (
            PRIORITY_LEVELS.get(x['priority'], 0),
            x['name']
        ), reverse=True)
        
        # Raggruppa per priorità
        by_priority = {'high': [], 'medium': [], 'low': []}
        for item in items_list:
            by_priority[item['priority']].append(item)
        
        return {
            'success': True,
            'items': items_list,
            'total_items': len(items_list),
            'by_priority': by_priority,
            'high_priority_count': len(by_priority['high']),
            'medium_priority_count': len(by_priority['medium']),
            'low_priority_count': len(by_priority['low'])
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': str(e),
            'items': [],
            'total_items': 0
        }


def calculate_shopping_frequency(user_id):
    """
    Calcola frequenza media shopping in giorni
    
    Returns:
        float: Media giorni tra spese (None se < 2 liste)
    """
    try:
        completed_lists = ShoppingList.query.filter_by(
            user_id=user_id,
            completed=True
        ).order_by(ShoppingList.completed_at.desc()).limit(10).all()
        
        if len(completed_lists) < 2:
            return None
        
        intervals = []
        for i in range(len(completed_lists) - 1):
            delta = completed_lists[i].completed_at - completed_lists[i+1].completed_at
            intervals.append(delta.days)
        
        return sum(intervals) / len(intervals) if intervals else None
        
    except Exception as e:
        print(f"calculate_shopping_frequency error: {e}")
        return None


# ========================================
# GAMIFICATION - PUNTI E REWARD
# ========================================

def award_points(user_id, action_type, amount=None):
    """
    Assegna punti all'utente
    
    Args:
        user_id: ID utente
        action_type: Tipo azione (vedi POINTS_TABLE)
        amount: Punti custom (opzionale)
    
    Returns:
        {
            'success': bool,
            'points_awarded': int,
            'new_total': int,
            'level_up': bool
        }
    """
    try:
        stats = UserStats.query.filter_by(user_id=user_id).first()
        
        if not stats:
            stats = UserStats(user_id=user_id)
            db.session.add(stats)
            db.session.flush()
        
        # Determina punti
        if amount is None:
            amount = POINTS_TABLE.get(action_type, 0)
        
        old_points = stats.points
        old_level = stats.level
        
        # Assegna punti
        stats.points += amount
        
        # Calcola nuovo livello
        new_level = calculate_level(stats.points)
        level_up = new_level > old_level
        
        if level_up:
            stats.level = new_level
        
        # Salva reward history
        history = RewardHistory(
            user_id=user_id,
            reward_type='points',
            value=amount,
            description=f"Azione: {action_type}"
        )
        db.session.add(history)
        db.session.commit()
        
        return {
            'success': True,
            'points_awarded': amount,
            'new_total': stats.points,
            'level': stats.level,
            'level_up': level_up,
            'action_type': action_type
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'message': str(e),
            'points_awarded': 0
        }


def calculate_level(points):
    """
    Calcola livello da punti
    
    Scala logaritmica: livello = floor(sqrt(points/100))
    """
    import math
    if points < 0:
        return 1
    return max(1, int(math.sqrt(points / 100)) + 1)


def get_level_progress(points):
    """Calcola progresso verso prossimo livello (0-100%)"""
    current_level = calculate_level(points)
    points_for_current = (current_level - 1) ** 2 * 100
    points_for_next = current_level ** 2 * 100
    
    progress = ((points - points_for_current) / (points_for_next - points_for_current)) * 100
    
    return {
        'current_level': current_level,
        'current_points': points,
        'points_for_next_level': points_for_next,
        'points_needed': points_for_next - points,
        'progress_percentage': min(100, max(0, progress))
    }


def get_user_leaderboard(metric='points', top_n=10, timeframe='all'):
    """
    Classifica utenti
    
    Args:
        metric: 'points' | 'waste_reduction' | 'products_added'
        top_n: Numero utenti da mostrare
        timeframe: 'all' | 'week' | 'month'
    
    Returns:
        list of dict con rank, username, score
    """
    try:
        query = db.session.query(User, UserStats).join(UserStats)
        
        # Filtra per timeframe
        if timeframe == 'week':
            start_date = datetime.utcnow() - timedelta(days=7)
            query = query.filter(UserStats.updated_at >= start_date)
        elif timeframe == 'month':
            start_date = datetime.utcnow() - timedelta(days=30)
            query = query.filter(UserStats.updated_at >= start_date)
        
        # Ordina per metrica
        if metric == 'points':
            query = query.order_by(UserStats.points.desc())
        elif metric == 'waste_reduction':
            query = query.order_by(UserStats.waste_reduction_score.desc())
        elif metric == 'products_added':
            query = query.order_by(UserStats.total_products_added.desc())
        else:
            query = query.order_by(UserStats.points.desc())
        
        results = query.limit(top_n).all()
        
        leaderboard = []
        for rank, (user, stats) in enumerate(results, start=1):
            leaderboard.append({
                'rank': rank,
                'username': user.username,
                'points': stats.points,
                'level': stats.level,
                'waste_reduction_score': stats.waste_reduction_score,
                'products_added': stats.total_products_added
            })
        
        return leaderboard
        
    except Exception as e:
        print(f"get_user_leaderboard error: {e}")
        return []


# ========================================
# NUTRIZIONE
# ========================================

def calculate_nutritional_goals(user_id):
    """
    Calcola obiettivi nutrizionali personalizzati
    
    Usa formule:
    - BMR (Basal Metabolic Rate)
    - TDEE (Total Daily Energy Expenditure)
    - Macronutrienti bilanciati
    
    Returns:
        dict con daily_calories, daily_protein, daily_carbs, daily_fat, daily_fiber
    """
    try:
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        
        if not profile or not all([profile.age, profile.weight, profile.height]):
            return None
        
        # Calcola BMR (Mifflin-St Jeor)
        if profile.gender.lower() == 'male':
            bmr = (10 * profile.weight) + (6.25 * profile.height) - (5 * profile.age) + 5
        else:
            bmr = (10 * profile.weight) + (6.25 * profile.height) - (5 * profile.age) - 161
        
        # Applica activity multiplier
        multiplier = ACTIVITY_MULTIPLIERS.get(profile.activity_level, 1.55)
        tdee = bmr * multiplier
        
        # Adatta per obiettivo
        if profile.goal == 'lose_weight':
            daily_calories = tdee * 0.8  # Deficit 20%
        elif profile.goal == 'gain_weight':
            daily_calories = tdee * 1.15  # Surplus 15%
        elif profile.goal == 'muscle_gain':
            daily_calories = tdee * 1.1  # Surplus 10%
        else:  # maintain
            daily_calories = tdee
        
        # Calcola macronutrienti
        # Proteine: 1.6-2.2g/kg (usiamo 1.8g/kg)
        daily_protein = profile.weight * 1.8
        
        # Grassi: 25-30% calorie totali
        daily_fat = (daily_calories * 0.28) / 9  # 9 kcal per grammo
        
        # Carboidrati: calorie rimanenti
        protein_calories = daily_protein * 4
        fat_calories = daily_fat * 9
        carbs_calories = daily_calories - protein_calories - fat_calories
        daily_carbs = carbs_calories / 4  # 4 kcal per grammo
        
        # Fibre: 14g per 1000 kcal (standard)
        daily_fiber = (daily_calories / 1000) * 14
        
        # Salva nel database
        goals = NutritionalGoal.query.filter_by(user_id=user_id).first()
        
        if not goals:
            goals = NutritionalGoal(user_id=user_id)
            db.session.add(goals)
        
        goals.daily_calories = round(daily_calories, 0)
        goals.daily_protein = round(daily_protein, 1)
        goals.daily_carbs = round(daily_carbs, 1)
        goals.daily_fat = round(daily_fat, 1)
        goals.daily_fiber = round(daily_fiber, 1)
        
        db.session.commit()
        
        return {
            'daily_calories': goals.daily_calories,
            'daily_protein': goals.daily_protein,
            'daily_carbs': goals.daily_carbs,
            'daily_fat': goals.daily_fat,
            'daily_fiber': goals.daily_fiber,
            'bmr': round(bmr, 0),
            'tdee': round(tdee, 0)
        }
        
    except Exception as e:
        db.session.rollback()
        print(f"calculate_nutritional_goals error: {e}")
        return None


# ========================================
# NOTIFICHE INTELLIGENTI
# ========================================

def smart_notification_system(user_id):
    """
    Sistema notifiche contestuali
    
    Returns:
        list of notifications con type, title, message, priority
    """
    notifications = []
    
    try:
        # 1. Prodotti in scadenza immediata (0-3 giorni)
        expiring_critical = get_expiring_products(user_id, days=3)
        if expiring_critical:
            notifications.append({
                'type': 'danger',
                'title': 'Prodotti in Scadenza Immediata',
                'message': f'{len(expiring_critical)} prodotti scadono nei prossimi 3 giorni',
                'action': 'view_expiring',
                'priority': 'high',
                'count': len(expiring_critical)
            })
        
        # 2. Prodotti in scadenza prossima (4-7 giorni)
        expiring_soon = len(get_expiring_products(user_id, days=7)) - len(expiring_critical)
        if expiring_soon > 0:
            notifications.append({
                'type': 'warning',
                'title': 'Prodotti in Scadenza',
                'message': f'{expiring_soon} prodotti scadono questa settimana',
                'action': 'view_expiring',
                'priority': 'medium',
                'count': expiring_soon
            })
        
        # 3. Scorte basse
        low_stock = get_low_stock_products(user_id)
        if low_stock:
            notifications.append({
                'type': 'info',
                'title': 'Scorte in Esaurimento',
                'message': f'{len(low_stock)} prodotti sotto soglia minima',
                'action': 'view_low_stock',
                'priority': 'medium',
                'count': len(low_stock)
            })
        
        # 4. Profilo nutrizionale incompleto
        profile = NutritionalProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            notifications.append({
                'type': 'info',
                'title': 'Completa il Profilo Nutrizionale',
                'message': 'Ricevi suggerimenti personalizzati completando il tuo profilo',
                'action': 'nutritional_profile',
                'priority': 'low'
            })
        
        # 5. Obiettivi nutrizionali non calcolati
        if profile and not NutritionalGoal.query.filter_by(user_id=user_id).first():
            notifications.append({
                'type': 'info',
                'title': 'Calcola Obiettivi Nutrizionali',
                'message': 'Imposta i tuoi obiettivi giornalieri per tracciare i progressi',
                'action': 'calculate_goals',
                'priority': 'low'
            })
        
        # Ordina per priorità
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        notifications.sort(key=lambda x: priority_order.get(x['priority'], 3))
        
        return notifications
        
    except Exception as e:
        print(f"smart_notification_system error: {e}")
        return []


# ========================================
# MEAL PLAN HELPERS
# ========================================

def auto_update_shopping_from_meal_plan(user_id, meal_plan_id):
    """
    Analizza meal plan e suggerisce ingredienti mancanti
    
    Returns:
        {
            'success': bool,
            'missing_ingredients': list,
            'already_available': list
        }
    """
    try:
        meal_plan = MealPlan.query.get(meal_plan_id)
        
        if not meal_plan or meal_plan.user_id != user_id:
            return {'success': False, 'message': 'Meal plan non trovato'}
        
        # Parsing ingredienti (supporta formati JSON in meal_plan.custom_meal)
        # Atteso: custom_meal possa contenere un campo JSON con chiave "ingredients"
        # es: {"ingredients": [{"item": "Pasta", "quantity": 200, "unit": "g"}, ...]}
        parsed_ingredients = _parse_meal_plan_ingredients(meal_plan)
        missing, available = _split_missing_vs_available(user_id, parsed_ingredients)
        
        return {
            'success': True,
            'missing_ingredients': missing,
            'already_available': available,
            'message': 'Analisi completata'
        }
        
    except Exception as e:
        return {'success': False, 'message': str(e)}


def _parse_meal_plan_ingredients(meal_plan):
    """Estrae ingredienti dal MealPlan.
    Strategia:
    - se custom_meal è JSON con key "ingredients", usa quello
    - altrimenti prova a stimare ingredienti basilari da testo (placeholder)
    Ritorna lista di dict: {item, quantity, unit}
    """
    ingredients = []
    try:
        if meal_plan.custom_meal:
            text = meal_plan.custom_meal.strip()
            # JSON?
            try:
                data = json.loads(text)
                if isinstance(data, dict) and isinstance(data.get('ingredients'), list):
                    for ing in data['ingredients']:
                        name = (ing.get('item') or '').strip()
                        qty = float(ing.get('quantity') or 0)
                        unit = (ing.get('unit') or '').strip() or 'unit'
                        if name and qty > 0:
                            ingredients.append({'item': name, 'quantity': qty, 'unit': unit})
                    return ingredients
            except Exception:
                pass
        # Fallback semplice: nessun parsing dal testo libero
        return ingredients
    except Exception:
        return []


def _split_missing_vs_available(user_id, ingredients):
    """Divide ingredienti tra disponibili in dispensa e mancanti.
    Disponibile se in dispensa esiste Product con quantità sufficiente.
    """
    missing = []
    available = []
    try:
        # Mappa prodotti disponibili per nome normalizzato
        products = Product.query.filter_by(user_id=user_id, wasted=False).all()
        name_to_product = {p.name.strip().lower(): p for p in products}
        for ing in ingredients:
            name = (ing.get('item') or '').strip()
            qty = float(ing.get('quantity') or 0)
            unit = (ing.get('unit') or '').strip()
            if not name or qty <= 0:
                continue
            key = name.lower()
            prod = name_to_product.get(key)
            if prod and prod.unit == unit and prod.quantity >= qty:
                available.append({'item': name, 'quantity': qty, 'unit': unit})
            else:
                # Mancante o insufficiente: aggiungi quantità richiesta
                missing.append({'item': name, 'quantity': qty, 'unit': unit})
        return missing, available
    except Exception:
        return ingredients, []


def upsert_missing_ingredients_to_shopping_list(user_id, missing_ingredients, shopping_list_id=None):
    """Crea/Aggiorna ShoppingItem per ogni ingrediente mancante.
    - Se esiste una ShoppingList non completata, la usa; altrimenti ne crea una.
    - Somma quantità se l'item esiste già.
    Ritorna (shopping_list, items_creati_o_aggiornati)
    """
    # Trova o crea shopping list
    shopping_list = None
    if shopping_list_id:
        shopping_list = ShoppingList.query.filter_by(id=shopping_list_id, user_id=user_id, completed=False).first()
    if not shopping_list:
        shopping_list = ShoppingList.query.filter_by(user_id=user_id, completed=False).order_by(ShoppingList.created_at.desc()).first()
    if not shopping_list:
        shopping_list = ShoppingList(user_id=user_id, name='Lista spesa', is_smart=True)
        db.session.add(shopping_list)
        db.session.flush()

    name_to_item = { (i.name.strip().lower(), i.unit): i for i in shopping_list.items }
    updated_items = []
    for ing in missing_ingredients:
        name = (ing.get('item') or '').strip()
        qty = float(ing.get('quantity') or 0)
        unit = (ing.get('unit') or '').strip() or 'unit'
        if not name or qty <= 0:
            continue
        key = (name.lower(), unit)
        item = name_to_item.get(key)
        if item:
            item.quantity = (item.quantity or 0) + qty
        else:
            item = ShoppingItem(
                shopping_list_id=shopping_list.id,
                name=name,
                quantity=qty,
                unit=unit,
                category=None,
                priority=PRIORITY_LEVELS.get('medium', 1)
            )
            db.session.add(item)
            name_to_item[key] = item
        updated_items.append({'name': name, 'quantity': qty, 'unit': unit})

    db.session.commit()
    return shopping_list, updated_items