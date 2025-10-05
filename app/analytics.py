"""
Analytics Module - FoodFlow
Calcolo analytics avanzate per dashboard e reports
"""

from datetime import datetime, timedelta
import json
from sqlalchemy import func

from .models import (
    db, Product, ShoppingList, ShoppingItem,
    DailyNutrition, WasteAnalytics, ShoppingAnalytics,
    MealPlan, NutritionalGoal
)


# ========================================
# COMPREHENSIVE ANALYTICS
# ========================================

def get_comprehensive_analytics(user_id, days=30):
    """
    Analytics complete per dashboard
    
    Args:
        user_id: ID utente
        days: Periodo in giorni
    
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
            'nutrition': calculate_nutrition_analytics(nutrition_data),
            'waste': calculate_waste_analytics(waste_data),
            'shopping': calculate_shopping_analytics(shopping_data),
            'trends': calculate_trends(user_id, days),
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days
            }
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

def calculate_nutrition_analytics(nutrition_data):
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
        'days_tracked': days_count
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
        'days_tracked': 0
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