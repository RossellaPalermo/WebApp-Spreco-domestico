"""
Analytics Module - FoodFlow
Calcolo analytics avanzate per dashboard e reports
"""

from datetime import datetime, timedelta
import json
from sqlalchemy import func
from flask import current_app

from .models import (
    db, Product, ShoppingList, ShoppingItem,
    DailyNutrition, WasteAnalytics, ShoppingAnalytics,
    MealPlan, NutritionalGoal
)


# ========================================
# COMPREHENSIVE ANALYTICS
# ========================================

def get_comprehensive_analytics(user_id, days=30, include_family=False):
    """
    Analytics complete per dashboard
    
    Args:
        user_id: ID utente
        days: Periodo in giorni
        include_family: Se True, include anche i dati familiari condivisi
    
    Returns:
        dict con nutrition, waste, shopping, trends
    """
    try:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        # Query dati periodo
        nutrition_data = DailyNutrition.query.filter(
            DailyNutrition.user_id == user_id,
            DailyNutrition.date >= start_date,
            DailyNutrition.date <= end_date
        ).all()
        
        waste_data = WasteAnalytics.query.filter(
            WasteAnalytics.user_id == user_id,
            WasteAnalytics.date >= start_date,
            WasteAnalytics.date <= end_date
        ).all()
        
        shopping_data = ShoppingAnalytics.query.filter(
            ShoppingAnalytics.user_id == user_id,
            ShoppingAnalytics.date >= start_date,
            ShoppingAnalytics.date <= end_date
        ).all()
        
        return {
            'nutrition': calculate_nutrition_analytics(nutrition_data, include_family),
            'waste': calculate_waste_analytics(waste_data),
            'shopping': calculate_shopping_analytics(shopping_data),
            'trends': calculate_trends(user_id, days),
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days
            },
            'scope': 'family' if include_family else 'personal'
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'nutrition': _empty_nutrition_analytics(),
            'waste': _empty_waste_analytics(),
            'shopping': _empty_shopping_analytics(),
            'trends': _empty_trends()
        }


# ========================================
# NUTRITION ANALYTICS
# ========================================

def calculate_nutrition_analytics(nutrition_data, include_family=False):
    """Calcola metriche nutrizionali"""
    if not nutrition_data:
        return _empty_nutrition_analytics()
    
    days_count = len(nutrition_data)
    
    total_calories = sum(d.calories_consumed for d in nutrition_data)
    total_protein = sum(d.protein_consumed for d in nutrition_data)
    total_carbs = sum(d.carbs_consumed for d in nutrition_data)
    total_fat = sum(d.fat_consumed for d in nutrition_data)
    total_fiber = sum(d.fiber_consumed for d in nutrition_data)
    
    goal_completion = sum(d.goal_completion_percentage for d in nutrition_data) / days_count
    consistency_score = sum(d.consistency_score for d in nutrition_data) / days_count
    
    return {
        'avg_calories': round(total_calories / days_count, 1),
        'avg_protein': round(total_protein / days_count, 1),
        'avg_carbs': round(total_carbs / days_count, 1),
        'avg_fat': round(total_fat / days_count, 1),
        'avg_fiber': round(total_fiber / days_count, 1),
        'goal_completion': round(goal_completion, 1),
        'consistency_score': round(consistency_score, 1),
        'days_tracked': days_count,
        'scope': 'family' if include_family else 'personal'
    }


def _empty_nutrition_analytics():
    """Ritorna analytics nutrizionali vuote"""
    return {
        'avg_calories': 0,
        'avg_protein': 0,
        'avg_carbs': 0,
        'avg_fat': 0,
        'avg_fiber': 0,
        'goal_completion': 0,
        'consistency_score': 0,
        'days_tracked': 0,
        'scope': 'personal'
    }


# ========================================
# WASTE ANALYTICS
# ========================================

def calculate_waste_analytics(waste_data):
    """Calcola metriche sprechi"""
    if not waste_data:
        return _empty_waste_analytics()
    
    days_count = len(waste_data)
    
    total_products_wasted = sum(d.products_wasted for d in waste_data)
    total_kg_wasted = sum(d.kg_wasted for d in waste_data)
    total_cost = sum(d.estimated_cost for d in waste_data)
    avg_daily_waste = total_kg_wasted / days_count if days_count > 0 else 0
    
    # Calcola trend (recente vs vecchio)
    waste_trend = 0
    if len(waste_data) >= 14:
        recent_week = waste_data[-7:]
        older_week = waste_data[-14:-7]
        
        recent_kg = sum(d.kg_wasted for d in recent_week)
        older_kg = sum(d.kg_wasted for d in older_week)
        
        if older_kg > 0:
            waste_trend = ((recent_kg - older_kg) / older_kg) * 100
    
    # Categoria più sprecata
    category_totals = _parse_category_breakdown(waste_data, "category_breakdown")
    most_wasted = max(category_totals, key=category_totals.get) if category_totals else "N/A"
    
    return {
        'total_products_wasted': total_products_wasted,
        'total_kg_wasted': round(total_kg_wasted, 2),
        'total_cost': round(total_cost, 2),
        'avg_daily_waste': round(avg_daily_waste, 2),
        'waste_trend': round(waste_trend, 1),
        'most_wasted_category': most_wasted,
        'category_breakdown': category_totals
    }


def _empty_waste_analytics():
    """Ritorna analytics sprechi vuote"""
    return {
        'total_products_wasted': 0,
        'total_kg_wasted': 0,
        'total_cost': 0,
        'avg_daily_waste': 0,
        'waste_trend': 0,
        'most_wasted_category': 'N/A',
        'category_breakdown': {}
    }


# ========================================
# SHOPPING ANALYTICS
# ========================================

def calculate_shopping_analytics(shopping_data):
    """Calcola metriche shopping"""
    if not shopping_data:
        return _empty_shopping_analytics()
    
    days_count = len(shopping_data)
    
    total_items = sum(d.items_purchased for d in shopping_data)
    total_cost = sum(d.estimated_cost for d in shopping_data)
    avg_items = total_items / days_count if days_count > 0 else 0
    
    ai_used = sum(d.ai_suggestions_used for d in shopping_data)
    ai_adoption_rate = (ai_used / total_items * 100) if total_items > 0 else 0
    
    # Categoria più acquistata
    category_totals = _parse_category_breakdown(shopping_data, "category_breakdown")
    most_purchased = max(category_totals, key=category_totals.get) if category_totals else "N/A"
    
    return {
        'total_items_purchased': total_items,
        'total_cost': round(total_cost, 2),
        'avg_items_per_trip': round(avg_items, 1),
        'ai_adoption_rate': round(ai_adoption_rate, 1),
        'most_purchased_category': most_purchased,
        'category_breakdown': category_totals
    }


def _empty_shopping_analytics():
    """Ritorna analytics shopping vuote"""
    return {
        'total_items_purchased': 0,
        'total_cost': 0,
        'avg_items_per_trip': 0,
        'ai_adoption_rate': 0,
        'most_purchased_category': 'N/A',
        'category_breakdown': {}
    }


# ========================================
# TRENDS ANALYTICS
# ========================================

def calculate_trends(user_id, days=30):
    """Calcola trends temporali"""
    try:
        # Prodotti aggiunti nel tempo
        products_trend = _get_products_trend(user_id, days)
        
        # Sprechi nel tempo
        waste_trend = _get_waste_trend(user_id, days)
        
        # Shopping nel tempo
        shopping_trend = _get_shopping_trend(user_id, days)
        
        return {
            'products_trend': products_trend,
            'waste_trend': waste_trend,
            'shopping_trend': shopping_trend
        }
        
    except Exception as e:
        return _empty_trends()


def _get_products_trend(user_id, days):
    """Trend prodotti aggiunti"""
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    
    # Raggruppa per giorno
    results = db.session.query(
        func.date(Product.created_at).label('date'),
        func.count(Product.id).label('count')
    ).filter(
        Product.user_id == user_id,
        Product.created_at >= start_date
    ).group_by('date').order_by('date').all()
    
    return [
        {'date': date.isoformat(), 'count': count}
        for date, count in results
    ]


def _get_waste_trend(user_id, days):
    """Trend sprechi"""
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    
    results = WasteAnalytics.query.filter(
        WasteAnalytics.user_id == user_id,
        WasteAnalytics.date >= start_date
    ).order_by(WasteAnalytics.date).all()
    
    return [
        {
            'date': r.date.isoformat(),
            'kg_wasted': float(r.kg_wasted),
            'cost': float(r.estimated_cost)
        }
        for r in results
    ]


def _get_shopping_trend(user_id, days):
    """Trend shopping"""
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    
    # Conta liste completate per giorno
    results = db.session.query(
        func.date(ShoppingList.completed_at).label('date'),
        func.count(ShoppingList.id).label('count'),
        func.sum(ShoppingList.actual_spent).label('total_spent')
    ).filter(
        ShoppingList.user_id == user_id,
        ShoppingList.completed == True,
        ShoppingList.completed_at >= start_date
    ).group_by('date').order_by('date').all()
    
    return [
        {
            'date': date.isoformat(),
            'trips': count,
            'spent': float(total_spent or 0)
        }
        for date, count, total_spent in results
    ]


def _empty_trends():
    """Ritorna trends vuote"""
    return {
        'products_trend': [],
        'waste_trend': [],
        'shopping_trend': []
    }


# ========================================
# WEEKLY REPORT
# ========================================

def generate_weekly_report(user_id):
    """
    Report settimanale completo
    
    Returns:
        dict con pantry, nutrition, waste, shopping, score, recommendations
    """
    try:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=7)
        
        # Analisi componenti
        pantry = _analyze_weekly_pantry(user_id, start_date, end_date)
        nutrition = _analyze_weekly_nutrition(user_id, start_date, end_date)
        waste = _analyze_weekly_waste(user_id, start_date, end_date)
        shopping = _analyze_weekly_shopping(user_id, start_date, end_date)
        
        # Score complessivo
        score = _calculate_weekly_score(pantry, nutrition, waste, shopping)
        
        # Raccomandazioni
        recommendations = _generate_weekly_recommendations(pantry, nutrition, waste, shopping)
        
        return {
            'success': True,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'pantry': pantry,
            'nutrition': nutrition,
            'waste': waste,
            'shopping': shopping,
            'overall_score': score,
            'recommendations': recommendations
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': str(e)
        }


def _analyze_weekly_pantry(user_id, start_date, end_date):
    """Analizza dispensa settimana"""
    total = Product.query.filter_by(user_id=user_id, wasted=False).count()
    
    expiring = Product.query.filter(
        Product.user_id == user_id,
        Product.expiry_date <= end_date + timedelta(days=7),
        Product.wasted == False
    ).count()
    
    low_stock = Product.query.filter(
        Product.user_id == user_id,
        Product.quantity <= Product.min_quantity,
        Product.wasted == False
    ).all()
    
    return {
        'total_products': total,
        'expiring': expiring,
        'low_stock': [{'name': p.name, 'quantity': p.quantity, 'unit': p.unit} for p in low_stock]
    }


def _analyze_weekly_nutrition(user_id, start_date, end_date):
    """Analizza nutrizione settimana"""
    nutrition_data = DailyNutrition.query.filter(
        DailyNutrition.user_id == user_id,
        DailyNutrition.date >= start_date,
        DailyNutrition.date <= end_date
    ).all()
    
    if not nutrition_data:
        return {'goal_completion': 0, 'days_tracked': 0}
    
    avg_completion = sum(d.goal_completion_percentage for d in nutrition_data) / len(nutrition_data)
    
    # Confronto con goals
    goals = NutritionalGoal.query.filter_by(user_id=user_id).first()
    goals_comparison = {}
    
    if goals:
        total_cals = sum(d.calories_consumed for d in nutrition_data)
        total_protein = sum(d.protein_consumed for d in nutrition_data)
        
        goals_comparison = {
            'calories': {
                'consumed': round(total_cals / len(nutrition_data), 1),
                'goal': goals.daily_calories,
                'percentage': round((total_cals / len(nutrition_data)) / goals.daily_calories * 100, 1)
            },
            'protein': {
                'consumed': round(total_protein / len(nutrition_data), 1),
                'goal': goals.daily_protein,
                'percentage': round((total_protein / len(nutrition_data)) / goals.daily_protein * 100, 1)
            }
        }
    
    return {
        'goal_completion': round(avg_completion, 1),
        'days_tracked': len(nutrition_data),
        'weekly_analysis': {
            'goals_comparison': goals_comparison
        }
    }


def _analyze_weekly_waste(user_id, start_date, end_date):
    """Analizza sprechi settimana"""
    wasted = Product.query.filter(
        Product.user_id == user_id,
        Product.wasted == True,
        Product.updated_at >= start_date
    ).all()
    
    total_kg = sum(p.quantity for p in wasted if p.unit in ['kg', 'g'])
    
    return {
        'wasted_products': len(wasted),
        'kg_wasted': round(total_kg, 2),
        'total_waste_kg': round(total_kg, 2),  # Alias per compatibilità
        'cost': 0,  # TODO: calcolo costo stimato
        'waste_trend': 0  # TODO: confronto settimana precedente
    }


def _analyze_weekly_shopping(user_id, start_date, end_date):
    """Analizza shopping settimana"""
    lists = ShoppingList.query.filter(
        ShoppingList.user_id == user_id,
        ShoppingList.completed == True,
        ShoppingList.completed_at >= start_date,
        ShoppingList.completed_at <= end_date
    ).all()
    
    total_items = sum(l.items.count() for l in lists)
    total_cost = sum(l.actual_spent for l in lists)
    
    return {
        'items_purchased': total_items,
        'cost': round(total_cost, 2),
        'trips': len(lists)
    }


def _calculate_weekly_score(pantry, nutrition, waste, shopping):
    """Calcola score settimanale (0-100)"""
    scores = []
    
    # Nutrition score (40% peso)
    if nutrition.get('goal_completion'):
        scores.append(nutrition['goal_completion'] * 0.4)
    
    # Waste score (40% peso) - inverso
    waste_kg = waste.get('kg_wasted', 0)
    waste_score = max(0, 100 - (waste_kg * 10))  # -10 punti per kg
    scores.append(waste_score * 0.4)
    
    # Pantry score (20% peso)
    expiring_pct = (pantry.get('expiring', 0) / max(pantry.get('total_products', 1), 1)) * 100
    pantry_score = max(0, 100 - expiring_pct)
    scores.append(pantry_score * 0.2)
    
    return round(sum(scores), 1)


def _generate_weekly_recommendations(pantry, nutrition, waste, shopping):
    """Genera raccomandazioni personalizzate"""
    recommendations = []
    
    # Nutrizione
    if nutrition.get('goal_completion', 0) < 80:
        recommendations.append({
            'category': 'nutrition',
            'priority': 'high',
            'title': 'Migliora il Tracking Nutrizionale',
            'message': f'Hai raggiunto solo il {nutrition.get("goal_completion", 0)}% degli obiettivi settimanali',
            'action': 'meal_planning'
        })
    
    # Sprechi
    if waste.get('kg_wasted', 0) > 2:
        recommendations.append({
            'category': 'waste',
            'priority': 'high',
            'title': 'Riduci gli Sprechi',
            'message': f'Hai sprecato {waste.get("kg_wasted", 0)} kg questa settimana',
            'action': 'reduce_waste'
        })
    
    # Scorte basse
    low_stock = pantry.get('low_stock', [])
    if len(low_stock) > 3:
        recommendations.append({
            'category': 'pantry',
            'priority': 'medium',
            'title': 'Rifornisci la Dispensa',
            'message': f'{len(low_stock)} prodotti in esaurimento',
            'action': 'restock_pantry'
        })
    
    return recommendations


# ========================================
# HELPER FUNCTIONS
# ========================================

def _parse_category_breakdown(data_list, attr_name):
    """Somma breakdown per categoria da JSON"""
    totals = {}
    
    for item in data_list:
        raw = getattr(item, attr_name, None)
        if not raw:
            continue
        
        try:
            breakdown = json.loads(raw) if isinstance(raw, str) else raw
            
            for category, amount in breakdown.items():
                totals[category] = totals.get(category, 0) + amount
                
        except (json.JSONDecodeError, AttributeError):
            continue
    
    return totals


# ========================================
# DATA UPDATERS - FUNZIONI PER POPOLARE ANALYTICS
# ========================================

def update_daily_nutrition(user_id, date=None, include_family=False):
    """
    Aggiorna i dati nutrizionali giornalieri
    
    Args:
        user_id: ID utente
        date: Data (default: oggi)
        include_family: Se True, include anche i pasti condivisi della famiglia
    """
    if date is None:
        date = datetime.utcnow().date()
    
    try:
        # Calcola nutrienti consumati dai meal plan del giorno
        if include_family:
            # Include pasti personali + condivisi della famiglia
            from .smart_functions import get_user_family
            
            # Pasti personali (non condivisi)
            personal_meals = MealPlan.query.filter(
                MealPlan.user_id == user_id,
                MealPlan.date == date,
                MealPlan.is_shared == False
            ).all()
            
            # Pasti condivisi della famiglia (inclusi quelli dell'utente corrente)
            family = get_user_family(user_id)
            family_shared_meals = []
            if family:
                member_ids = [member.user_id for member in family.members]
                family_shared_meals = MealPlan.query.filter(
                    MealPlan.user_id.in_(member_ids),
                    MealPlan.date == date,
                    MealPlan.is_shared == True
                ).all()
            
            # Per pasti condivisi, dividi le calorie per il numero di membri della famiglia
            family_size = family.members.count() if family else 1
            
            total_calories = 0
            total_protein = 0
            total_carbs = 0
            total_fat = 0
            total_fiber = 0
            
            # Aggiungi pasti personali (non condivisi)
            for mp in personal_meals:
                total_calories += mp.calories or 0
                total_protein += mp.protein or 0
                total_carbs += mp.carbs or 0
                total_fat += mp.fat or 0
                total_fiber += mp.fiber or 0
            
            # Aggiungi pasti condivisi della famiglia (divisi per numero membri)
            for mp in family_shared_meals:
                if family_size > 1:
                    total_calories += (mp.calories or 0) / family_size
                    total_protein += (mp.protein or 0) / family_size
                    total_carbs += (mp.carbs or 0) / family_size
                    total_fat += (mp.fat or 0) / family_size
                    total_fiber += (mp.fiber or 0) / family_size
                else:
                    total_calories += mp.calories or 0
                    total_protein += mp.protein or 0
                    total_carbs += mp.carbs or 0
                    total_fat += mp.fat or 0
                    total_fiber += mp.fiber or 0
        else:
            # Solo pasti personali dell'utente (non condivisi)
            meal_plans = MealPlan.query.filter(
                MealPlan.user_id == user_id,
                MealPlan.date == date,
                MealPlan.is_shared == False
            ).all()
            
            total_calories = sum(mp.calories or 0 for mp in meal_plans)
            total_protein = sum(mp.protein or 0 for mp in meal_plans)
            total_carbs = sum(mp.carbs or 0 for mp in meal_plans)
            total_fat = sum(mp.fat or 0 for mp in meal_plans)
            total_fiber = sum(mp.fiber or 0 for mp in meal_plans)
        
        # Ottieni obiettivi nutrizionali
        goals = NutritionalGoal.query.filter_by(user_id=user_id).first()
        if goals:
            calories_goal = goals.daily_calories
            protein_goal = goals.daily_protein
            carbs_goal = goals.daily_carbs
            fat_goal = goals.daily_fat
            fiber_goal = goals.daily_fiber
        else:
            # Valori di default
            calories_goal = 2000.0
            protein_goal = 150.0
            carbs_goal = 250.0
            fat_goal = 65.0
            fiber_goal = 25.0
        
        # Calcola percentuale completamento
        goal_completion = 0
        if calories_goal > 0:
            goal_completion = min(100, (total_calories / calories_goal) * 100)
        
        # Trova o crea record
        nutrition = DailyNutrition.query.filter_by(
            user_id=user_id, 
            date=date
        ).first()
        
        if not nutrition:
            nutrition = DailyNutrition(
                user_id=user_id,
                date=date
            )
            db.session.add(nutrition)
        
        # Aggiorna dati
        nutrition.calories_consumed = total_calories
        nutrition.protein_consumed = total_protein
        nutrition.carbs_consumed = total_carbs
        nutrition.fat_consumed = total_fat
        nutrition.fiber_consumed = total_fiber
        nutrition.calories_goal = calories_goal
        nutrition.protein_goal = protein_goal
        nutrition.carbs_goal = carbs_goal
        nutrition.fat_goal = fat_goal
        nutrition.fiber_goal = fiber_goal
        nutrition.goal_completion_percentage = goal_completion
        
        # Calcola consistency score (media ultimi 7 giorni)
        consistency_score = calculate_consistency_score(user_id, date)
        nutrition.consistency_score = consistency_score
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating daily nutrition: {e}")
        return False


def update_waste_analytics(user_id, date=None):
    """
    Aggiorna i dati di spreco giornalieri
    """
    if date is None:
        date = datetime.utcnow().date()
    
    try:
        # Calcola prodotti sprecati del giorno
        wasted_products = Product.query.filter(
            Product.user_id == user_id,
            Product.wasted == True,
            func.date(Product.updated_at) == date
        ).all()
        
        total_products = len(wasted_products)
        total_kg = sum(p.quantity or 0 for p in wasted_products)
        # Stima costo basato su prezzi medi per categoria (senza price_per_unit)
        total_cost = total_kg * 5.0  # Stima 5€/kg come media
        
        # Calcola breakdown per categoria
        category_breakdown = {}
        for product in wasted_products:
            category = product.category or 'Altro'
            if category not in category_breakdown:
                category_breakdown[category] = {'count': 0, 'kg': 0, 'cost': 0}
            category_breakdown[category]['count'] += 1
            category_breakdown[category]['kg'] += product.quantity or 0
            category_breakdown[category]['cost'] += (product.quantity or 0) * 5.0  # Stima 5€/kg
        
        # Trova categoria più sprecata
        most_wasted_category = None
        if category_breakdown:
            most_wasted_category = max(category_breakdown.keys(), 
                                     key=lambda k: category_breakdown[k]['kg'])
        
        # Calcola trend (confronto con giorno precedente)
        yesterday = date - timedelta(days=1)
        yesterday_waste = WasteAnalytics.query.filter_by(
            user_id=user_id, 
            date=yesterday
        ).first()
        
        waste_trend = 0
        if yesterday_waste and yesterday_waste.kg_wasted > 0:
            waste_trend = ((total_kg - yesterday_waste.kg_wasted) / yesterday_waste.kg_wasted) * 100
        
        # Trova o crea record
        waste_analytics = WasteAnalytics.query.filter_by(
            user_id=user_id, 
            date=date
        ).first()
        
        if not waste_analytics:
            waste_analytics = WasteAnalytics(
                user_id=user_id,
                date=date
            )
            db.session.add(waste_analytics)
        
        # Aggiorna dati
        waste_analytics.products_wasted = total_products
        waste_analytics.kg_wasted = total_kg
        waste_analytics.estimated_cost = total_cost
        waste_analytics.category_breakdown = json.dumps(category_breakdown)
        waste_analytics.waste_trend = waste_trend
        waste_analytics.most_wasted_category = most_wasted_category
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating waste analytics: {e}")
        return False


def update_shopping_analytics(user_id, date=None):
    """
    Aggiorna i dati di shopping giornalieri
    """
    if date is None:
        date = datetime.utcnow().date()
    
    try:
        # Calcola shopping completati del giorno
        completed_lists = ShoppingList.query.filter(
            ShoppingList.user_id == user_id,
            ShoppingList.completed == True,
            func.date(ShoppingList.completed_at) == date
        ).all()
        
        total_items = 0
        total_cost = 0
        ai_suggestions_used = 0
        
        # Calcola breakdown per categoria
        category_breakdown = {}
        
        for shopping_list in completed_lists:
            if shopping_list.is_smart:
                ai_suggestions_used += 1
            
            for item in shopping_list.items:
                total_items += 1
                item_cost = (item.quantity or 0) * (item.estimated_price or 0)
                total_cost += item_cost
                
                category = item.category or 'Altro'
                if category not in category_breakdown:
                    category_breakdown[category] = {'count': 0, 'cost': 0}
                category_breakdown[category]['count'] += 1
                category_breakdown[category]['cost'] += item_cost
        
        # Trova categoria più acquistata
        most_purchased_category = None
        if category_breakdown:
            most_purchased_category = max(category_breakdown.keys(), 
                                        key=lambda k: category_breakdown[k]['count'])
        
        # Calcola frequenza shopping (giorni tra acquisti)
        shopping_frequency = calculate_shopping_frequency(user_id, date)
        
        # Trova o crea record
        shopping_analytics = ShoppingAnalytics.query.filter_by(
            user_id=user_id, 
            date=date
        ).first()
        
        if not shopping_analytics:
            shopping_analytics = ShoppingAnalytics(
                user_id=user_id,
                date=date
            )
            db.session.add(shopping_analytics)
        
        # Aggiorna dati
        shopping_analytics.items_purchased = total_items
        shopping_analytics.estimated_cost = total_cost
        shopping_analytics.category_breakdown = json.dumps(category_breakdown)
        shopping_analytics.ai_suggestions_used = ai_suggestions_used
        shopping_analytics.most_purchased_category = most_purchased_category
        shopping_analytics.shopping_frequency_days = shopping_frequency
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating shopping analytics: {e}")
        return False


def calculate_consistency_score(user_id, date, days=7):
    """
    Calcola score di consistenza nutrizionale (0-100)
    """
    try:
        start_date = date - timedelta(days=days-1)
        
        nutrition_records = DailyNutrition.query.filter(
            DailyNutrition.user_id == user_id,
            DailyNutrition.date >= start_date,
            DailyNutrition.date <= date
        ).all()
        
        if not nutrition_records:
            return 0
        
        # Calcola media completamento obiettivi
        total_completion = sum(r.goal_completion_percentage or 0 for r in nutrition_records)
        avg_completion = total_completion / len(nutrition_records)
        
        # Score basato su completamento e consistenza
        consistency_score = min(100, avg_completion)
        
        return round(consistency_score, 1)
        
    except Exception as e:
        current_app.logger.error(f"Error calculating consistency score: {e}")
        return 0


def calculate_shopping_frequency(user_id, date, days=30):
    """
    Calcola frequenza media di shopping (giorni tra acquisti)
    """
    try:
        start_date = date - timedelta(days=days)
        
        completed_shopping = ShoppingList.query.filter(
            ShoppingList.user_id == user_id,
            ShoppingList.completed == True,
            ShoppingList.completed_at >= start_date,
            ShoppingList.completed_at <= date
        ).order_by(ShoppingList.completed_at).all()
        
        if len(completed_shopping) < 2:
            return 0
        
        # Calcola giorni tra acquisti
        total_days = 0
        for i in range(1, len(completed_shopping)):
            days_between = (completed_shopping[i].completed_at - completed_shopping[i-1].completed_at).days
            total_days += days_between
        
        avg_frequency = total_days / (len(completed_shopping) - 1)
        return round(avg_frequency, 1)
        
    except Exception as e:
        current_app.logger.error(f"Error calculating shopping frequency: {e}")
        return 0


def update_all_analytics(user_id, date=None):
    """
    Aggiorna tutti i dati analytics per un utente
    """
    if date is None:
        date = datetime.utcnow().date()
    
    results = {
        'nutrition': update_daily_nutrition(user_id, date),
        'waste': update_waste_analytics(user_id, date),
        'shopping': update_shopping_analytics(user_id, date)
    }
    
    return results


def _prepare_charts_data(analytics_data):
    """
    Prepara i dati per i grafici Chart.js
    
    Args:
        analytics_data: Dati analytics completi
    
    Returns:
        dict: Dati formattati per Chart.js
    """
    try:
        charts_data = {}
        
        # Nutrition Chart (Line Chart)
        nutrition_data = analytics_data.get('nutrition', {})
        if nutrition_data:
            charts_data['nutrition'] = {
                'labels': ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'],
                'datasets': [{
                    'label': 'Completamento Obiettivi (%)',
                    'data': [nutrition_data.get('goal_completion', 0)] * 7,  # Placeholder
                    'borderColor': '#00D563',
                    'backgroundColor': 'rgba(0, 213, 99, 0.1)',
                    'tension': 0.4
                }]
            }
        
        # Waste Chart (Doughnut Chart)
        waste_data = analytics_data.get('waste', {})
        if waste_data:
            charts_data['waste'] = {
                'labels': ['Sprechi', 'Risparmi'],
                'datasets': [{
                    'data': [
                        waste_data.get('total_kg_wasted', 0),
                        max(0, 10 - waste_data.get('total_kg_wasted', 0))  # Placeholder
                    ],
                    'backgroundColor': ['#EF4444', '#10B981'],
                    'borderWidth': 0
                }]
            }
        
        # Shopping Chart (Bar Chart)
        shopping_data = analytics_data.get('shopping', {})
        if shopping_data:
            charts_data['shopping'] = {
                'labels': ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu'],
                'datasets': [{
                    'label': 'Items Acquistati',
                    'data': [shopping_data.get('total_items_purchased', 0)] * 6,  # Placeholder
                    'backgroundColor': '#3B82F6',
                    'borderColor': '#1D4ED8',
                    'borderWidth': 1
                }]
            }
        
        # Category Chart (Pie Chart)
        charts_data['category'] = {
            'labels': ['Frutta', 'Verdura', 'Carne', 'Latticini', 'Altro'],
            'datasets': [{
                'data': [25, 20, 15, 20, 20],  # Placeholder
                'backgroundColor': [
                    '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57'
                ],
                'borderWidth': 0
            }]
        }
        
        # Savings Chart (Line Chart)
        charts_data['savings'] = {
            'labels': ['Sett 1', 'Sett 2', 'Sett 3', 'Sett 4'],
            'datasets': [{
                'label': 'Risparmi (€)',
                'data': [10, 15, 12, 18],  # Placeholder
                'borderColor': '#10B981',
                'backgroundColor': 'rgba(16, 185, 129, 0.1)',
                'tension': 0.4
            }]
        }
        
        # Timeline Chart (Multi-line Chart)
        charts_data['timeline'] = {
            'labels': ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'],
            'datasets': [
                {
                    'label': 'Calorie',
                    'data': [2000, 2100, 1900, 2200, 2000, 1800, 2000],
                    'borderColor': '#00D563',
                    'backgroundColor': 'rgba(0, 213, 99, 0.1)',
                    'yAxisID': 'y'
                },
                {
                    'label': 'Sprechi (kg)',
                    'data': [0.5, 0.3, 0.8, 0.2, 0.4, 0.1, 0.3],
                    'borderColor': '#EF4444',
                    'backgroundColor': 'rgba(239, 68, 68, 0.1)',
                    'yAxisID': 'y1'
                }
            ]
        }
        
        return charts_data
        
    except Exception as e:
        current_app.logger.error(f"Error preparing charts data: {e}")
        return {}