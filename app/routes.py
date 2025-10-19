"""
FoodFlow Routes
Gestisce tutte le routes dell'applicazione
"""

import re
import json
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from sqlalchemy import func

from . import db
from .models import (
    User, Product, ShoppingList, ShoppingItem, UserStats,
    Badge, UserBadge, NutritionalProfile,
    NutritionalGoal, MealPlan, Family, FamilyMember
)

from .smart_functions import (
    get_expiring_products, get_low_stock_products, get_expired_products,
    get_recycling_suggestions, award_points, calculate_waste_reduction_score,
    calculate_nutritional_goals, smart_notification_system,
    auto_update_shopping_from_meal_plan, upsert_missing_ingredients_to_shopping_list,
    create_family, join_family, get_user_family, get_family_members,
    get_combined_products, get_combined_meal_plans, leave_family
)

from .ai_functions import (
    suggest_recipes,
    ai_optimize_meal_planning,
    ai_suggest_shopping_list,
    ai_generate_recipe_suggestions,
    ai_chatbot_response
)

from .analytics import get_comprehensive_analytics, _prepare_charts_data, update_all_analytics


# ========================================
# HELPER FUNCTIONS
# ========================================

def validate_email(email):
    """Valida formato email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password_strength(password):
    """Valida robustezza password"""
    if len(password) < 8:
        return False, "La password deve essere di almeno 8 caratteri"
    if not re.search(r'[A-Z]', password):
        return False, "Deve contenere almeno una lettera maiuscola"
    if not re.search(r'[a-z]', password):
        return False, "Deve contenere almeno una lettera minuscola"
    if not re.search(r'\d', password):
        return False, "Deve contenere almeno un numero"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Deve contenere almeno un carattere speciale"
    return True, ""


def validate_username(username):
    """Valida username"""
    if len(username) < 3:
        return False, "Lo username deve essere di almeno 3 caratteri"
    if len(username) > 20:
        return False, "Lo username non può superare i 20 caratteri"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Lo username può contenere solo lettere, numeri e underscore"
    return True, ""


# ========================================
# HELPER FUNCTION PER CHARTS
# ========================================

def _prepare_charts_data(analytics_data):
    """
    Trasforma i dati analytics in formato Chart.js
    
    Args:
        analytics_data: dict ritornato da get_comprehensive_analytics
    
    Returns:
        dict con datasets per ogni grafico
    """
    try:
        # Estrai trends
        trends = analytics_data.get('trends', {})
        waste_trend = trends.get('waste_trend', [])
        products_trend = trends.get('products_trend', [])
        
        # NUTRITION CHART (Doughnut)
        nutrition = analytics_data.get('nutrition', {})
        nutrition_chart = {
            'labels': ['Proteine', 'Carboidrati', 'Grassi', 'Fibre'],
            'datasets': [{
                'data': [
                    nutrition.get('avg_protein', 0),
                    nutrition.get('avg_carbs', 0),
                    nutrition.get('avg_fat', 0),
                    nutrition.get('avg_fiber', 0)
                ],
                'backgroundColor': [
                    '#10B981',  # success
                    '#3B82F6',  # info
                    '#F59E0B',  # warning
                    '#9C27B0'   # purple
                ],
                'borderWidth': 0
            }]
        }
        
        # WASTE CHART (Line)
        waste_labels = [w.get('date', '')[-5:] for w in waste_trend]  # MM-DD
        waste_data = [w.get('kg_wasted', 0) for w in waste_trend]
        waste_chart = {
            'labels': waste_labels,
            'datasets': [{
                'label': 'Kg Sprecati',
                'data': waste_data,
                'borderColor': '#EF4444',
                'backgroundColor': 'rgba(239,68,68,0.1)',
                'tension': 0.4,
                'fill': True,
                'pointRadius': 4,
                'pointHoverRadius': 6,
                'pointBackgroundColor': '#EF4444'
            }]
        }
        
        # SHOPPING CHART (Bar)
        shopping = analytics_data.get('shopping', {})
        shopping_chart = {
            'labels': ['Totali', 'AI Usati'],
            'datasets': [{
                'data': [
                    shopping.get('total_items_purchased', 0),
                    int(shopping.get('total_items_purchased', 0) * 
                        shopping.get('ai_adoption_rate', 0) / 100)
                ],
                'backgroundColor': ['#3B82F6', '#00D563'],
                'borderRadius': 8
            }]
        }
        
        # CATEGORY CHART (Polar)
        waste = analytics_data.get('waste', {})
        categories = waste.get('category_breakdown', {})
        category_labels = list(categories.keys())[:5] or ['Frutta', 'Verdura', 'Latticini', 'Carne', 'Altro']
        category_values = list(categories.values())[:5] or [25, 20, 15, 10, 30]
        
        category_chart = {
            'labels': category_labels,
            'datasets': [{
                'data': category_values,
                'backgroundColor': [
                    '#10B981',
                    '#00D563',
                    '#3B82F6',
                    '#EF4444',
                    '#F59E0B'
                ]
            }]
        }
        
        # SAVINGS CHART (Doughnut)
        shopping_cost = shopping.get('total_cost', 0)
        waste_cost = waste.get('total_cost', 0)
        saved = max(0, shopping_cost - waste_cost)
        
        savings_chart = {
            'labels': ['Risparmiato', 'Sprecato'],
            'datasets': [{
                'data': [saved, waste_cost],
                'backgroundColor': ['#10B981', '#EF4444'],
                'borderWidth': 0
            }]
        }
        
        # TIMELINE CHART (Line)
        timeline_labels = [p.get('date', '')[-5:] for p in products_trend] if products_trend else []
        timeline_data = [p.get('count', 0) for p in products_trend] if products_trend else []
        
        timeline_chart = {
            'labels': timeline_labels,
            'datasets': [{
                'label': 'Prodotti in Dispensa',
                'data': timeline_data,
                'borderColor': '#00D563',
                'backgroundColor': 'rgba(0,213,99,0.1)',
                'tension': 0.4,
                'fill': True
            }]
        }
        
        return {
            'nutrition': nutrition_chart,
            'waste': waste_chart,
            'shopping': shopping_chart,
            'category': category_chart,
            'savings': savings_chart,
            'timeline': timeline_chart
        }
        
    except Exception as e:
        current_app.logger.error(f"Error preparing charts data: {e}")
        return {}




# ========================================
# ROUTE REGISTRATION
# ========================================
def register_routes(app):
    """Registra tutte le routes dell'applicazione"""
    
    # ===== HOMEPAGE =====
    @app.route('/')
    def index():
        """Homepage / Dashboard"""
        if not current_user.is_authenticated:
            return render_template('index_modern.html')
        
        try:
            # Recupera dati dashboard
            expiring_products = get_expiring_products(current_user.id, days=7)  # Prossimi 7 giorni
            low_stock_products = get_low_stock_products(current_user.id)
            expired_products = get_expired_products(current_user.id, days_overdue=0)  # Scaduti oggi o prima
            
            # Debug logging
            current_app.logger.info(f"Dashboard - Expiring products: {len(expiring_products)}")
            current_app.logger.info(f"Dashboard - Expired products: {len(expired_products)}")
            current_app.logger.info(f"Dashboard - Low stock products: {len(low_stock_products)}")
            recycling_data = get_recycling_suggestions(current_user.id)
            recycling_suggestions = recycling_data.get('suggestions', []) if isinstance(recycling_data, dict) else []
            
            # User stats (crea se non esiste)
            stats = UserStats.query.filter_by(user_id=current_user.id).first()
            if not stats:
                stats = UserStats(user_id=current_user.id)
                db.session.add(stats)
                db.session.commit()
            
            # Altri dati
            waste_score = calculate_waste_reduction_score(current_user.id)
            
            badges = [
                Badge.query.get(ub.badge_id)
                for ub in UserBadge.query.filter_by(user_id=current_user.id).all()
                if Badge.query.get(ub.badge_id)
            ]
            
            ai_shopping_data = ai_suggest_shopping_list(current_user.id)
            ai_shopping_suggestions = ai_shopping_data.get("suggestions", [])[:3]
            
            ai_meal_plan = ai_optimize_meal_planning(current_user.id)
            for day in ai_meal_plan:
                ai_meal_plan[day] = ai_meal_plan[day][:3]
            
            nutritional_profile = NutritionalProfile.query.filter_by(user_id=current_user.id).first()
            nutritional_goals = NutritionalGoal.query.filter_by(user_id=current_user.id).first()
            
            # Aggiorna analytics nutrizionali se necessario (solo dati personali per dashboard)
            from .analytics import update_daily_nutrition
            today = datetime.now().date()
            update_daily_nutrition(current_user.id, today, include_family=False)
            
            analytics = get_comprehensive_analytics(current_user.id, days=30, include_family=False)
            smart_notifications = smart_notification_system(current_user.id)
            shopping_lists = ShoppingList.query.filter_by(user_id=current_user.id).limit(5).all()
            
            return render_template(
                'dashboard_modern.html',
                expiring_products=expiring_products,
                low_stock_products=low_stock_products,
                expired_products=expired_products,
                recycling_suggestions=recycling_suggestions,
                stats=stats,
                waste_score=waste_score,
                badges=badges,
                ai_shopping_suggestions=ai_shopping_suggestions,
                ai_meal_plan=ai_meal_plan,
                nutritional_profile=nutritional_profile,
                nutritional_goals=nutritional_goals,
                analytics=analytics,
                smart_notifications=smart_notifications,
                shopping_lists=shopping_lists,
                today=datetime.now().date()
            )
            
        except Exception as e:
            app.logger.error(f"Error loading dashboard: {e}")
            flash('Errore nel caricamento della dashboard', 'danger')
            
            # ✅ CORREZIONE: Inizializza tutte le variabili necessarie anche in caso di errore
            stats = UserStats.query.filter_by(user_id=current_user.id).first()
            if not stats:
                stats = UserStats(user_id=current_user.id)
                db.session.add(stats)
                try:
                    db.session.commit()
                except:
                    db.session.rollback()
            
            # Valori di fallback per tutte le variabili
            return render_template(
                'dashboard_modern.html',
                expiring_products=[],
                low_stock_products=[],
                expired_products=[],
                recycling_suggestions=[],
                stats=stats,
                waste_score=0,
                badges=[],
                ai_shopping_suggestions=[],
                ai_meal_plan={},
                nutritional_profile=None,
                nutritional_goals=None,
                analytics={
                    'nutrition': {'goal_completion': 0, 'avg_calories': 0, 'avg_protein': 0, 'avg_carbs': 0, 'avg_fat': 0, 'avg_fiber': 0},
                    'waste': {'total_kg_wasted': 0, 'total_cost': 0},
                    'shopping': {'total_items_purchased': 0},
                    'trends': {'waste_trend': [], 'products_trend': []}
                },
                smart_notifications=[],
                shopping_lists=[],
                today=datetime.now().date()
            )
    
    # ========================================
    # ANALYTICS
    # ========================================
    
    @app.route('/analytics')
    @login_required
    def analytics():
        """Pagina analytics"""
        from .models import Product, MealPlan, UserStats
        
        # Crea analytics semplici basate sui dati esistenti
        products = Product.query.filter_by(user_id=current_user.id).all()
        meals = MealPlan.query.filter_by(user_id=current_user.id).all()
        stats = UserStats.query.filter_by(user_id=current_user.id).first()
        
        if not stats:
            stats = UserStats(user_id=current_user.id)
            db.session.add(stats)
            db.session.commit()
        
        # Calcola dati reali
        total_products = len(products)
        total_meals = len(meals)
        wasted_products = [p for p in products if p.wasted]
        total_wasted_kg = sum(p.quantity for p in wasted_products if p.quantity)
        total_wasted_cost = total_wasted_kg * 5.0  # Stima 5€/kg
        
        # Calcola calorie totali dai meal plans
        total_calories = sum(m.calories or 0 for m in meals)
        avg_calories = total_calories / max(1, total_meals) if total_meals > 0 else 0
        
        # Crea analytics data
        analytics_data = {
            'nutrition': {
                'goal_completion': min(100, (avg_calories / 2000) * 100) if avg_calories > 0 else 0,
                'avg_calories': round(avg_calories, 1),
                'avg_protein': round(sum(m.protein or 0 for m in meals) / max(1, total_meals), 1),
                'avg_carbs': round(sum(m.carbs or 0 for m in meals) / max(1, total_meals), 1),
                'avg_fat': round(sum(m.fat or 0 for m in meals) / max(1, total_meals), 1),
                'avg_fiber': round(sum(m.fiber or 0 for m in meals) / max(1, total_meals), 1)
            },
            'waste': {
                'total_kg_wasted': round(total_wasted_kg, 1),
                'total_cost': round(total_wasted_cost, 2),
                'total_products_wasted': len(wasted_products)
            },
            'shopping': {
                'total_items_purchased': total_products,
                'total_cost': round(total_products * 3.0, 2)  # Stima 3€ per prodotto
            },
            'trends': {
                'waste_trend': [len(wasted_products)],
                'products_trend': [total_products]
            }
        }
        
        return render_template('analytics.html', analytics=analytics_data)



    @app.route('/api/meal/<int:meal_id>/details')
    @login_required
    def api_meal_details(meal_id):
        """API per ottenere dettagli completi di un pasto"""
        try:
            from .models import MealPlan
            
            meal = MealPlan.query.filter_by(id=meal_id, user_id=current_user.id).first()
            if not meal:
                return jsonify({'success': False, 'message': 'Pasto non trovato'}), 404
            
            # Genera ricetta e procedimento se non esistono
            # Controlla se i campi esistono (per compatibilità con database non migrato)
            has_recipe = hasattr(meal, 'recipe')
            has_procedure = hasattr(meal, 'procedure')
            has_ai_generated = hasattr(meal, 'ai_generated')
            
            if not has_recipe or not has_procedure:
                # Simula generazione ricetta basata sul nome del pasto
                recipe, procedure = generate_recipe_for_meal(meal.custom_meal)
                if has_recipe:
                    meal.recipe = recipe
                if has_procedure:
                    meal.procedure = procedure
                if has_ai_generated:
                    meal.ai_generated = False
                db.session.commit()
            
            # Genera ricetta e procedimento se i campi non esistono
            recipe = getattr(meal, 'recipe', None) or generate_recipe_for_meal(meal.custom_meal)[0]
            procedure = getattr(meal, 'procedure', None) or generate_recipe_for_meal(meal.custom_meal)[1]
            ai_generated = getattr(meal, 'ai_generated', False)
            
            return jsonify({
                'success': True,
                'meal': {
                    'id': meal.id,
                    'name': meal.custom_meal,
                    'date': meal.date.isoformat(),
                    'meal_type': meal.meal_type,
                    'servings': meal.servings,
                    'calories': meal.calories,
                    'protein': meal.protein,
                    'carbs': meal.carbs,
                    'fat': meal.fat,
                    'fiber': meal.fiber,
                    'recipe': recipe,
                    'procedure': procedure,
                    'ai_generated': ai_generated
                }
            })
        except Exception as e:
            current_app.logger.error(f"Meal details API error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    def generate_recipe_for_meal(meal_name):
        """Genera ricetta e procedimento per un pasto"""
        # Lista di ingredienti comuni per tipo di pasto
        ingredients_map = {
            'pasta': ['Pasta', 'Pomodoro', 'Aglio', 'Basilico', 'Olio extravergine', 'Parmigiano'],
            'risotto': ['Riso', 'Brodo vegetale', 'Cipolla', 'Parmigiano', 'Burro', 'Vino bianco'],
            'pollo': ['Petto di pollo', 'Olio', 'Spezie', 'Limone', 'Rosmarino'],
            'pesce': ['Filetto di pesce', 'Olio', 'Limone', 'Erbe aromatiche', 'Sale'],
            'insalata': ['Lattuga', 'Pomodori', 'Cetrioli', 'Olio', 'Aceto', 'Sale'],
            'pizza': ['Farina', 'Lievito', 'Pomodoro', 'Mozzarella', 'Basilico', 'Olio']
        }
        
        # Trova ingredienti appropriati
        ingredients = []
        for key, items in ingredients_map.items():
            if key in meal_name.lower():
                ingredients = items
                break
        
        if not ingredients:
            ingredients = ['Ingredienti base', 'Olio', 'Sale', 'Pepe', 'Spezie']
        
        recipe = f"Ingredienti per {meal_name}:\n" + "\n".join([f"• {ing}" for ing in ingredients])
        
        procedure = f"""Procedimento per {meal_name}:

1. Preparare tutti gli ingredienti
2. Riscaldare una padella con un filo d'olio
3. Cuocere gli ingredienti principali per 10-15 minuti
4. Aggiungere le spezie e i condimenti
5. Mescolare bene e servire caldo

Tempo di preparazione: 20-30 minuti
Difficoltà: Media"""
        
        return recipe, procedure

    @app.route('/api/analytics/export')
    @login_required
    def api_analytics_export():
        """Esporta dati analytics base in CSV."""
        import csv
        from io import StringIO

        days = request.args.get('days', default=30, type=int)
        data = get_comprehensive_analytics(current_user.id, days=days)

        output = StringIO()
        writer = csv.writer(output, delimiter=';')

        writer.writerow(['Section', 'Metric', 'Value'])
        for key, val in (data.get('nutrition') or {}).items():
            writer.writerow(['nutrition', key, val])
        for key, val in (data.get('waste') or {}).items():
            writer.writerow(['waste', key, val])
        for key, val in (data.get('shopping') or {}).items():
            writer.writerow(['shopping', key, val])

        csv_bytes = output.getvalue().encode('utf-8')
        return current_app.response_class(
            csv_bytes,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=analytics.csv'}
        )
    
    # ========================================
    # AUTENTICAZIONE
    # ========================================
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login utente"""
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('Inserisci username e password', 'danger')
                return render_template('login.html')
            
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                flash(f'Benvenuto, {user.username}!', 'success')
                
                # Redirect a pagina richiesta o dashboard
                next_page = request.args.get('next')
                return redirect(next_page if next_page else url_for('index'))
            
            flash('Username o password non corretti', 'danger')
        
        return render_template('login.html')
    
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """Registrazione nuovo utente"""
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Validazione campi vuoti
            if not all([username, email, password, confirm_password]):
                flash('Tutti i campi sono obbligatori', 'danger')
                return render_template('register.html')
            
            # Validazione username
            is_valid, error_msg = validate_username(username)
            if not is_valid:
                flash(error_msg, 'danger')
                return render_template('register.html')
            
            # Validazione email
            if not validate_email(email):
                flash('Formato email non valido', 'danger')
                return render_template('register.html')
            
            # Validazione password match
            if password != confirm_password:
                flash('Le password non coincidono', 'danger')
                return render_template('register.html')
            
            # Validazione robustezza password
            is_valid, error_msg = validate_password_strength(password)
            if not is_valid:
                flash(error_msg, 'danger')
                return render_template('register.html')
            
            # Controllo duplicati
            if User.query.filter(func.lower(User.username) == username.lower()).first():
                flash('Username già esistente', 'danger')
                return render_template('register.html')
            
            if User.query.filter_by(email=email).first():
                flash('Email già registrata', 'danger')
                return render_template('register.html')
            
            # Creazione utente
            try:
                user = User(
                    username=username,
                    email=email,
                    password_hash=generate_password_hash(password, method='pbkdf2:sha256')
                )
                db.session.add(user)
                
                # Crea stats iniziali senza flush esplicito (relazione gestita da SQLAlchemy)
                stats = UserStats(user=user)
                db.session.add(stats)
                
                db.session.commit()
                
                # Auto-login
                login_user(user)
                
                flash(f'Benvenuto su FoodFlow, {username}!', 'success')
                return redirect(url_for('index'))
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Registration error: {e}")
                flash('Errore durante la registrazione. Riprova', 'danger')
                return render_template('register.html')
        
        return render_template('register.html')
    
    
    @app.route('/logout')
    @login_required
    def logout():
        """Logout utente"""
        logout_user()
        flash('Logout effettuato con successo', 'success')
        return redirect(url_for('index'))
    
    
    # ========================================
    # DISPENSA
    # ========================================
    
    @app.route('/products')
    @login_required
    def products():
        """Lista prodotti dispensa (personali + condivisi famiglia)"""
        products = get_combined_products(current_user.id)
        
        return render_template(
            'products.html',
            products=products,
            today=datetime.now().date()
        )
    
    
    @app.route('/products/add', methods=['GET', 'POST'])
    @login_required
    def add_product():
        """Aggiungi prodotto"""
        if request.method == 'POST':
            try:
                # Validazione e sanitizzazione
                name = request.form['name'].strip().title()
                
                if not re.match(r'^[a-zA-Z0-9àèéìòùÀÈÉÌÒÙ\s\-\'\.]+$', name):
                    flash('Il nome contiene caratteri non validi', 'danger')
                    return render_template('add_product.html')
                
                quantity = float(request.form['quantity'])
                if quantity <= 0:
                    flash('La quantità deve essere maggiore di zero', 'danger')
                    return render_template('add_product.html')
                
                # Data scadenza
                expiry_date_str = request.form.get('expiry_date', '').strip()
                if not expiry_date_str:
                    flash('Data di scadenza obbligatoria', 'danger')
                    return render_template('add_product.html')
                
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                
                if expiry_date < datetime.now().date():
                    flash('La data di scadenza non può essere nel passato', 'danger')
                    return render_template('add_product.html')
                
                # Controlla duplicati
                duplicate = Product.query.filter_by(
                    user_id=current_user.id,
                    name=name,
                    category=request.form['category'],
                    wasted=False
                ).first()
                
                if duplicate:
                    flash(f'Prodotto già presente. Quantità attuale: {duplicate.quantity} {duplicate.unit}', 'warning')
                    return render_template('add_product.html')
                
                # Crea prodotto
                product = Product(
                    user_id=current_user.id,
                    name=name,
                    quantity=quantity,
                    unit=request.form['unit'],
                    expiry_date=expiry_date,
                    category=request.form['category'],
                    min_quantity=float(request.form.get('min_quantity', 1)),
                    is_shared=request.form.get('is_shared') == 'on',  # Checkbox
                    allergens=request.form.get('allergens', '').strip(),
                    notes=request.form.get('notes', '').strip()
                )
                
                db.session.add(product)
                db.session.commit()
                
                # Gamification: no points for product addition per new policy
                
                # Aggiorna stats
                stats = UserStats.query.filter_by(user_id=current_user.id).first()
                if stats:
                    stats.total_products_added += 1
                    db.session.commit()
                
                # Aggiorna analytics
                update_all_analytics(current_user.id)
                
                flash(f'Prodotto "{name}" aggiunto con successo!', 'success')
                return redirect(url_for('products'))
                
            except ValueError as e:
                flash('Dati non validi. Controlla i campi inseriti', 'danger')
                return render_template('add_product.html')
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Add product error: {e}")
                flash('Errore nell\'aggiunta del prodotto', 'danger')
                return render_template('add_product.html')
        
        return render_template('add_product.html')
    
    
    @app.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
    @login_required
    def edit_product(product_id):
        """Modifica prodotto"""
        product = Product.query.get_or_404(product_id)
        
        if product.user_id != current_user.id:
            flash('Accesso negato', 'danger')
            return redirect(url_for('products'))
        
        if request.method == 'POST':
            try:
                product.name = request.form['name'].strip().title()
                product.quantity = float(request.form['quantity'])
                product.unit = request.form['unit']
                expiry_date_str = (request.form.get('expiry_date') or '').strip()
                product.expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
                product.category = request.form['category']
                product.min_quantity = float(request.form.get('min_quantity', 1))
                product.is_shared = request.form.get('is_shared') == 'on'  # Checkbox
                product.allergens = request.form.get('allergens', '').strip()
                product.notes = request.form.get('notes', '').strip()
                
                db.session.commit()
                
                flash('Prodotto aggiornato con successo!', 'success')
                return redirect(url_for('products'))
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Edit product error: {e}")
                flash('Errore nell\'aggiornamento', 'danger')
        
        return render_template('edit_product.html', product=product)
    
    
    @app.route('/products/delete/<int:product_id>', methods=['POST', 'DELETE'])
    @login_required
    def delete_product(product_id):
        """Elimina prodotto"""
        product = Product.query.get_or_404(product_id)
        
        if product.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Accesso negato'}), 403
        
        try:
            db.session.delete(product)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Prodotto eliminato con successo'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    
    @app.route('/products/waste/<int:product_id>', methods=['POST'])
    @login_required
    def waste_product(product_id):
        """Marca prodotto come sprecato"""
        product = Product.query.get_or_404(product_id)
        
        if product.user_id != current_user.id:
            return jsonify({'success': False}), 403
        
        try:
            waste_percentage = float(request.form.get('waste_percentage', 100))
            
            if waste_percentage >= 100:
                product.wasted = True
            else:
                product.quantity *= (1 - waste_percentage / 100)
            
            db.session.commit()
            
            # Aggiorna stats
            stats = UserStats.query.filter_by(user_id=current_user.id).first()
            if stats:
                stats.total_products_wasted += 1
                db.session.commit()
            
            points = int(5 * (waste_percentage / 100))
            award_points(current_user.id, 'waste_reduction', points)
            
            # Aggiorna analytics
            update_all_analytics(current_user.id)
            
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    
    @app.route('/products/recycle/<int:product_id>', methods=['POST'])
    @login_required
    def recycle_product(product_id):
        """Marca prodotto come riciclato e rimuove dalla dispensa"""
        product = Product.query.get_or_404(product_id)
        
        if product.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Accesso negato'}), 403
        
        try:
            # Marca come sprecato (riciclato)
            product.wasted = True
            
            db.session.commit()
            
            # Aggiorna stats
            stats = UserStats.query.filter_by(user_id=current_user.id).first()
            if stats:
                stats.total_products_wasted += 1
                db.session.commit()
            
            # Award points per riciclo
            award_points(current_user.id, 'recycling', 10)
            
            # Controlla badge di riciclo
            from .smart_functions import check_recycling_badges
            new_badges = check_recycling_badges(current_user.id)
            
            # Aggiorna analytics
            update_all_analytics(current_user.id)
            
            # Prepara messaggio con badge
            message = f'Prodotto "{product.name}" riciclato con successo!'
            if new_badges:
                badge_names = [badge.name for badge in new_badges]
                message += f' 🏆 Nuovo badge: {", ".join(badge_names)}!'
            
            return jsonify({
                'success': True, 
                'message': message,
                'new_badges': [{'name': badge.name, 'description': badge.description} for badge in new_badges]
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    
    # ========================================
    # SHOPPING LIST
    # ========================================
    
    @app.route('/shopping-list')
    @login_required
    def shopping_list():
        """Dashboard shopping list"""
        lists = ShoppingList.query.filter_by(user_id=current_user.id).order_by(
            ShoppingList.completed.asc(),
            ShoppingList.created_at.desc()
        ).all()
        
        return render_template('shopping_list.html', lists=lists)
    
    
    @app.route('/shopping-list/create', methods=['POST'])
    @login_required
    def create_shopping_list():
        """Crea nuova lista"""
        try:
            name = request.form.get('name', '').strip()
            
            if not name:
                return jsonify({'success': False, 'message': 'Nome obbligatorio'}), 400
            
            shopping_list = ShoppingList(
                user_id=current_user.id,
                name=name,
                store_name=request.form.get('store_name', '').strip(),
                budget=request.form.get('budget', type=float)
            )
            
            db.session.add(shopping_list)
            db.session.commit()
            
            award_points(current_user.id, 'shopping_list_created', 5)
            
            # Aggiorna analytics
            update_all_analytics(current_user.id)
            
            return jsonify({
                'success': True,
                'message': f'Lista "{name}" creata!',
                'list_id': shopping_list.id
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/shopping-list/generate-smart', methods=['POST'])
    @login_required
    def generate_smart_shopping_list():
        """Genera automaticamente una lista spesa usando suggerimenti AI e prodotti in esaurimento/scadenza."""
        try:
            # Ottieni suggerimenti AI (expiring + low stock)
            ai_data = ai_suggest_shopping_list(current_user.id)
            suggestions = ai_data.get('suggestions', []) if ai_data else []

            if not suggestions:
                return jsonify({'success': False, 'message': 'Nessun suggerimento disponibile al momento'}), 200

            # Crea una nuova lista
            list_name = f"Lista AI {datetime.now().strftime('%d/%m/%Y')}"
            shopping_list = ShoppingList(
                user_id=current_user.id,
                name=list_name,
                is_smart=True
            )
            db.session.add(shopping_list)
            db.session.flush()  # per ottenere l'id

            # Aggiungi items suggeriti con quantità/unità di default
            created = 0
            for name in suggestions:
                if not name:
                    continue
                item = ShoppingItem(
                    shopping_list_id=shopping_list.id,
                    name=name,
                    quantity=1.0,
                    unit='pz',
                    priority=1
                )
                db.session.add(item)
                created += 1

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Lista "{list_name}" creata con {created} suggerimenti',
                'list_id': shopping_list.id,
                'items_created': created
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    
    @app.route('/shopping-list/<int:list_id>/add-item', methods=['POST'])
    @login_required
    def add_shopping_item(list_id):
        """Aggiungi item a lista"""
        shopping_list = ShoppingList.query.get_or_404(list_id)
        
        if shopping_list.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Accesso negato'}), 403
        
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            quantity = float(data.get('quantity', 0))
            unit = data.get('unit', '').strip()
            
            if not all([name, quantity, unit]) or quantity <= 0:
                return jsonify({'success': False, 'message': 'Dati invalidi'}), 400
            
            # Controlla duplicati
            existing = shopping_list.items.filter_by(name=name, completed=False).first()
            
            if existing:
                existing.quantity += quantity
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': f'Quantità di {name} aggiornata'
                })
            
            # Crea nuovo item
            item = ShoppingItem(
                shopping_list_id=list_id,
                name=name,
                quantity=quantity,
                unit=unit,
                category=data.get('category'),
                priority=data.get('priority', 0),
                estimated_price=data.get('estimated_price'),
                notes=data.get('notes')
            )
            
            db.session.add(item)
            db.session.commit()
            
            # Aggiorna analytics
            update_all_analytics(current_user.id)
            
            return jsonify({
                'success': True,
                'message': f'{name} aggiunto',
                'item': item.to_dict()
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    
    @app.route('/shopping-list/item/<int:item_id>/toggle', methods=['POST'])
    @login_required
    def toggle_shopping_item(item_id):
        """Toggle completamento item"""
        item = ShoppingItem.query.get_or_404(item_id)
        
        if item.shopping_list.user_id != current_user.id:
            return jsonify({'success': False}), 403
        
        item.completed = not item.completed
        db.session.commit()
        
        return jsonify({
            'success': True,
            'completed': item.completed
        })

    @app.route('/shopping-list/item/<int:item_id>/delete', methods=['DELETE'])
    @login_required
    def delete_shopping_item(item_id):
        """Elimina un item dalla lista spesa"""
        item = ShoppingItem.query.get_or_404(item_id)
        if item.shopping_list.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Accesso negato'}), 403
        try:
            db.session.delete(item)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Elemento rimosso'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/shopping-list/<int:list_id>/delete', methods=['DELETE'])
    @login_required
    def delete_shopping_list(list_id):
        """Elimina una lista spesa."""
        shopping_list = ShoppingList.query.get_or_404(list_id)
        if shopping_list.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Accesso negato'}), 403
        try:
            db.session.delete(shopping_list)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Lista eliminata'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    
    @app.route('/shopping-list/<int:list_id>/complete', methods=['POST'])
    @login_required
    def complete_shopping_list(list_id):
        """Completa lista e aggiorna dispensa"""
        shopping_list = ShoppingList.query.get_or_404(list_id)
        
        if shopping_list.user_id != current_user.id:
            return jsonify({'success': False}), 403
        
        if shopping_list.completed:
            return jsonify({'success': False, 'message': 'Già completata'}), 400
        
        try:
            completed_items = shopping_list.items.filter_by(completed=True).all()
            
            if not completed_items:
                return jsonify({'success': False, 'message': 'Nessun item completato'}), 400
            
            added = 0
            updated = 0
            
            for item in completed_items:
                existing = Product.query.filter_by(
                    user_id=current_user.id,
                    name=item.name,
                    wasted=False
                ).first()
                
                if existing:
                    existing.quantity += item.quantity
                    updated += 1
                else:
                    new_product = Product(
                        user_id=current_user.id,
                        name=item.name,
                        quantity=item.quantity,
                        unit=item.unit,
                        category=item.category or 'Altro',
                        expiry_date=datetime.now().date() + timedelta(days=30),
                        min_quantity=item.quantity * 0.2
                    )
                    db.session.add(new_product)
                    added += 1
            
            shopping_list.completed = True
            shopping_list.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            points = (added + updated) * 2
            award_points(current_user.id, 'shopping_completed', points)
            
            return jsonify({
                'success': True,
                'message': f'{added} aggiunti, {updated} aggiornati',
                'points_earned': points
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    
    # ========================================
    # GAMIFICATION
    # ========================================
    
    @app.route('/gamification')
    @login_required
    def gamification():
        """Pagina gamification"""
        from .models import User, UserStats, UserBadge, Badge
        
        stats = UserStats.query.filter_by(user_id=current_user.id).first()
        
        if not stats:
            stats = UserStats(user_id=current_user.id)
            db.session.add(stats)
            db.session.commit()
        
        badges = [
            Badge.query.get(ub.badge_id)
            for ub in current_user.user_badges.all()
            if Badge.query.get(ub.badge_id)
        ]
        
        # Crea leaderboard semplice
        
        # Assicurati che tutti gli utenti abbiano UserStats
        all_users = User.query.all()
        for user in all_users:
            if not UserStats.query.filter_by(user_id=user.id).first():
                user_stats = UserStats(user_id=user.id)
                db.session.add(user_stats)
        db.session.commit()
        
        # Crea leaderboard semplice
        leaderboard_data = []
        for i, user in enumerate(all_users[:10], 1):  # Top 10 utenti
            user_stats = UserStats.query.filter_by(user_id=user.id).first()
            badges_count = UserBadge.query.filter_by(user_id=user.id).count()
            
            leaderboard_data.append({
                'rank': i,
                'user_id': user.id,
                'username': user.username,
                'points': user_stats.points if user_stats else 0,
                'level': user_stats.level if user_stats else 1,
                'badges_count': badges_count,
                'waste_reduction_score': user_stats.waste_reduction_score if user_stats else 0,
                'products_added': user_stats.total_products_added if user_stats else 0
            })
        
        # Ordina per punti
        leaderboard_data.sort(key=lambda x: x['points'], reverse=True)
        
        # Riassegna i rank
        for i, entry in enumerate(leaderboard_data, 1):
            entry['rank'] = i
        
        return render_template('gamification.html', stats=stats, badges=badges, leaderboard=leaderboard_data)

    
    
    # ========================================
    # PIANO NUTRIZIONALE
    # ========================================
    
    @app.route('/nutritional-profile', methods=['GET', 'POST'])
    @login_required
    def nutritional_profile():
        """Profilo nutrizionale"""
        if request.method == 'POST':
            try:
                profile = NutritionalProfile.query.filter_by(user_id=current_user.id).first()
                
                if not profile:
                    profile = NutritionalProfile(user_id=current_user.id)
                    db.session.add(profile)
                
                profile.age = int(request.form.get('age', 25))
                profile.weight = float(request.form.get('weight', 70))
                profile.height = float(request.form.get('height', 170))
                profile.gender = request.form.get('gender', 'male')
                profile.activity_level = request.form.get('activity_level', 'moderate')
                profile.goal = request.form.get('goal', 'maintain')

                # Normalizza restrizioni/allergie in JSON array (accetta CSV o JSON)
                def _to_json_array_string(raw_value):
                    raw_value = (raw_value or '').strip()
                    if not raw_value:
                        return '[]'
                    try:
                        # Se è già JSON valido, lo manteniamo
                        parsed = json.loads(raw_value)
                        if isinstance(parsed, list):
                            return json.dumps([str(v).strip() for v in parsed if str(v).strip()])
                    except Exception:
                        pass
                    # Fallback: interpreta come CSV / righe
                    tokens = []
                    for part in raw_value.replace('\n', ',').split(','):
                        token = part.strip()
                        if token:
                            tokens.append(token)
                    return json.dumps(tokens)

                # Gestisci restrizioni alimentari (checkbox multiple)
                dietary_restrictions = request.form.getlist('dietary_restrictions')
                profile.dietary_restrictions = json.dumps(dietary_restrictions) if dietary_restrictions else '[]'
                
                # Gestisci allergie
                profile.allergies = _to_json_array_string(request.form.get('allergies', ''))
                
                db.session.commit()
                
                calculate_nutritional_goals(current_user.id)
                
                flash('Profilo aggiornato con successo!', 'success')
                return redirect(url_for('nutritional_profile'))
                
            except Exception as e:
                db.session.rollback()
                flash('Errore nell\'aggiornamento', 'danger')
        
        profile = NutritionalProfile.query.filter_by(user_id=current_user.id).first()
        goals = NutritionalGoal.query.filter_by(user_id=current_user.id).first()
        
        return render_template('nutritional_profile.html', profile=profile, goals=goals)
    
    
    @app.route('/meal-planning', methods=['GET', 'POST'])
    @login_required
    def meal_planning():
        """Piano pasti"""
        if request.method == 'POST':
            try:
                raw_date = (request.form.get('date') or '').strip()
                meal_type = (request.form.get('meal_type') or 'lunch').strip()
                custom_meal = (request.form.get('custom_meal') or '').strip()
                servings = request.form.get('servings', type=int) or 2

                if not raw_date or not meal_type or not custom_meal:
                    flash('Compila data, tipo pasto e descrizione', 'warning')
                    return redirect(url_for('meal_planning'))

                parsed_date = datetime.strptime(raw_date, '%Y-%m-%d').date()

                meal_plan = MealPlan(
                    user_id=current_user.id,
                    date=parsed_date,
                    meal_type=meal_type,
                    custom_meal=custom_meal,
                    is_shared=request.form.get('is_shared') == 'on',  # Checkbox
                    servings=servings
                )
                db.session.add(meal_plan)
                db.session.flush()  # Per ottenere l'ID
                
                # Calcola valori nutrizionali con AI
                from .ai_functions import ai_estimate_meal_calories
                nutrition = ai_estimate_meal_calories(custom_meal, meal_type)
                
                # Salva per porzione e scala in base alle porzioni impostate
                per_serving_cals = float(nutrition['calories'] or 0)
                per_serving_pro = float(nutrition['protein'] or 0)
                per_serving_carbs = float(nutrition['carbs'] or 0)
                per_serving_fat = float(nutrition['fat'] or 0)
                per_serving_fiber = float(nutrition['fiber'] or 0)

                meal_plan.calories = per_serving_cals * servings
                meal_plan.protein = per_serving_pro * servings
                meal_plan.carbs = per_serving_carbs * servings
                meal_plan.fat = per_serving_fat * servings
                meal_plan.fiber = per_serving_fiber * servings
                
                db.session.commit()
                
                # Aggiorna analytics nutrizionali (solo personali per dashboard)
                from .analytics import update_daily_nutrition
                update_daily_nutrition(current_user.id, parsed_date, include_family=False)
                
                flash('Pasto aggiunto al piano!', 'success')
                return redirect(url_for('meal_planning'))

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"meal_planning POST error: {e}")
                flash('Errore nella creazione del pasto', 'danger')
                return redirect(url_for('meal_planning'))
        
        profile = NutritionalProfile.query.filter_by(user_id=current_user.id).first()
        goals = NutritionalGoal.query.filter_by(user_id=current_user.id).first()
        meal_plans = get_combined_meal_plans(current_user.id)
        
        # Analytics per meal planning (include dati familiari)
        from .analytics import get_comprehensive_analytics
        meal_analytics = get_comprehensive_analytics(current_user.id, days=30, include_family=True)
        # Serialize meal plans for frontend JSON usage
        meal_plans_json = [
            {
                'id': mp.id,
                'date': mp.date.isoformat() if mp.date else None,
                'meal_type': mp.meal_type,
                'custom_meal': mp.custom_meal,
                'calories': mp.calories,
                'protein': mp.protein,
                'carbs': mp.carbs,
                'fat': mp.fat,
                'fiber': mp.fiber,
                'servings': getattr(mp, 'servings', None)
            }
            for mp in meal_plans
        ]
        
        return render_template(
            'meal_planning.html',
            nutritional_profile=profile,
            nutritional_goals=goals,
            meal_plans=meal_plans,
            meal_plans_json=meal_plans_json,
            meal_analytics=meal_analytics,
            today=datetime.now().date()
        )
    
    


    # ========================================
    # RICICLO E SUGGERIMENTI
    # ========================================
    
    @app.route('/recycling-suggestions')
    @login_required
    def recycling_suggestions():
        """Pagina suggerimenti di riciclo per prodotti scaduti"""
        try:
            # Recupera prodotti scaduti
            expired_products = get_expired_products(current_user.id, days_overdue=7)
            
            # Recupera suggerimenti di riciclo
            recycling_data = get_recycling_suggestions(current_user.id)
            
            return render_template(
                'recycling_suggestions.html',
                expired_products=expired_products,
                recycling_suggestions=recycling_data.get('suggestions', []),
                total_products=recycling_data.get('total_products', 0),
                today=datetime.now().date()
            )
            
        except Exception as e:
            app.logger.error(f"Error loading recycling suggestions: {e}")
            flash('Errore nel caricamento dei suggerimenti di riciclo', 'danger')
            return render_template('recycling_suggestions.html', 
                                expired_products=[], 
                                recycling_suggestions=[], 
                                total_products=0)
    
    
    @app.route('/api/recycling-suggestions')
    @login_required
    def api_recycling_suggestions():
        """API per ottenere suggerimenti di riciclo"""
        try:
            recycling_data = get_recycling_suggestions(current_user.id)
            return jsonify(recycling_data)
            
        except Exception as e:
            app.logger.error(f"API recycling suggestions error: {e}")
            return jsonify({
                'success': False,
                'message': 'Errore nel recupero dei suggerimenti',
                'suggestions': []
            }), 500


    # ========================================
    # CHATBOT
    # ========================================
    
    @app.route('/chatbot')
    @login_required
    def chatbot():
        """Pagina chatbot"""
        return render_template('chatbot.html')
    
    
    @app.route('/api/chatbot/message', methods=['POST'])
    @login_required
    def api_chatbot_message():
        """API per inviare messaggi al chatbot"""
        try:
            data = request.get_json()
            user_message = data.get('message', '').strip()
            conversation_context = data.get('context', '')
            
            if not user_message:
                return jsonify({
                    'success': False,
                    'message': 'Messaggio vuoto'
                }), 400
            
            # Genera risposta con AI
            response = ai_chatbot_response(user_message, current_user.id, conversation_context)
            
            return jsonify(response)
            
        except Exception as e:
            app.logger.error(f"Chatbot API error: {e}")
            return jsonify({
                'success': False,
                'message': 'Errore nel chatbot',
                'response': 'Mi dispiace, si è verificato un errore. Riprova più tardi!'
            }), 500
    
    
    # ========================================
    # API ENDPOINTS
    # ========================================
    
    @app.route('/api/ai-recipes')
    @login_required
    def api_ai_recipes():
        """API ricette AI"""
        try:
            # Parametri opzionali
            servings = request.args.get('servings', type=int)
            recipes = suggest_recipes(current_user.id, servings=servings)
            
            expiring_products = Product.query.filter(
                Product.user_id == current_user.id,
                Product.expiry_date <= datetime.utcnow().date() + timedelta(days=7)
            ).all()
            
            expiring_based = []
            if expiring_products:
                ingredients = [(p.name, p.quantity, p.unit) for p in expiring_products]
                expiring_based = ai_generate_recipe_suggestions(ingredients, current_user.id, max_recipes=3)
            
            return jsonify({
                'success': True,
                'ingredients_based': recipes,
                'expiring_based': expiring_based
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'ingredients_based': [],
                'expiring_based': []
            }), 500

    @app.route('/api/ai-meal-plan', methods=['POST'])
    @login_required
    def api_ai_meal_plan():
        """API generazione piano pasti AI"""
        try:
            # Parametri
            days = request.json.get('days', 7) if request.is_json else 7
            servings = request.json.get('servings') if request.is_json else None
            share_with_family = bool(request.json.get('share_with_family')) if request.is_json else False
            
            # Genera piano pasti con AI
            meal_plan = ai_optimize_meal_planning(current_user.id, days)
            
            if not meal_plan:
                return jsonify({
                    'success': False,
                    'message': 'Impossibile generare piano pasti. Verifica di avere ingredienti nella dispensa.'
                }), 400
            
            # Salva piano pasti nel database
            saved_meals = []
            today = datetime.now().date()
            
            for day_offset, day_meals in meal_plan.items():
                for meal_data in day_meals:
                    meal_date = today + timedelta(days=day_offset)
                    
                    # Controlla se esiste già un pasto per questa data/tipo
                    existing = MealPlan.query.filter_by(
                        user_id=current_user.id,
                        date=meal_date,
                        meal_type=meal_data['meal_type']
                    ).first()
                    
                    if existing:
                        # Aggiorna pasto esistente
                        existing.custom_meal = meal_data['description']
                        existing.is_shared = share_with_family
                        base_cal = float(meal_data.get('calories', 0) or 0)
                        base_pro = float(meal_data.get('protein', 0) or 0)
                        base_car = float(meal_data.get('carbs', 0) or 0)
                        base_fat = float(meal_data.get('fat', 0) or 0)
                        if servings:
                            existing.calories = base_cal * int(servings)
                            existing.protein = base_pro * int(servings)
                            existing.carbs = base_car * int(servings)
                            existing.fat = base_fat * int(servings)
                            existing.servings = int(servings)
                        else:
                            existing.calories = base_cal
                            existing.protein = base_pro
                            existing.carbs = base_car
                            existing.fat = base_fat
                        saved_meals.append(existing)
                    else:
                        # Crea nuovo pasto
                        meal = MealPlan(
                            user_id=current_user.id,
                            date=meal_date,
                            meal_type=meal_data['meal_type'],
                            custom_meal=meal_data['description'],
                            is_shared=share_with_family,
                            calories=(float(meal_data.get('calories', 0) or 0) * int(servings) if servings else float(meal_data.get('calories', 0) or 0)),
                            protein=(float(meal_data.get('protein', 0) or 0) * int(servings) if servings else float(meal_data.get('protein', 0) or 0)),
                            carbs=(float(meal_data.get('carbs', 0) or 0) * int(servings) if servings else float(meal_data.get('carbs', 0) or 0)),
                            fat=(float(meal_data.get('fat', 0) or 0) * int(servings) if servings else float(meal_data.get('fat', 0) or 0)),
                            servings=(int(servings) if servings else None)
                        )
                        db.session.add(meal)
                        saved_meals.append(meal)
            
            db.session.commit()
            
            # Aggiorna analytics nutrizionali per tutti i giorni del piano (solo personali per dashboard)
            from .analytics import update_daily_nutrition
            for day_offset in meal_plan.keys():
                meal_date = today + timedelta(days=day_offset)
                update_daily_nutrition(current_user.id, meal_date, include_family=False)
            
            # Award points per generazione piano
            award_points(current_user.id, 'meal_plan_generated', 25)
            
            return jsonify({
                'success': True,
                'message': f'Piano pasti generato con successo! {len(saved_meals)} pasti creati.',
                'meals_created': len(saved_meals),
                'meal_plan': meal_plan
            })
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"AI meal plan generation error: {e}")
            return jsonify({
                'success': False,
                'message': 'Errore nella generazione del piano pasti'
            }), 500

    @app.route('/api/recalculate-calories/<int:meal_id>', methods=['POST'])
    @login_required
    def recalculate_calories(meal_id):
        """Ricalcola le calorie di un pasto con AI"""
        try:
            meal_plan = MealPlan.query.filter_by(id=meal_id, user_id=current_user.id).first()
            
            if not meal_plan:
                return jsonify({'success': False, 'message': 'Pasto non trovato'}), 404
            
            from .ai_functions import ai_estimate_meal_calories
            nutrition = ai_estimate_meal_calories(meal_plan.custom_meal, meal_plan.meal_type)
            
            meal_plan.calories = nutrition['calories']
            meal_plan.protein = nutrition['protein']
            meal_plan.carbs = nutrition['carbs']
            meal_plan.fat = nutrition['fat']
            meal_plan.fiber = nutrition['fiber']
            
            db.session.commit()
            
            # Aggiorna analytics nutrizionali (solo personali per dashboard)
            from .analytics import update_daily_nutrition
            update_daily_nutrition(current_user.id, meal_plan.date, include_family=False)
            
            return jsonify({
                'success': True,
                'message': 'Calorie ricalcolate con successo!',
                'nutrition': nutrition
            })
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"recalculate_calories error: {e}")
            return jsonify({
                'success': False,
                'message': 'Errore nel ricalcolo delle calorie'
            }), 500

    # ========================================
    # INTEGRAZIONI MEAL PLAN / LISTA / DISPENSA
    # ========================================

    @app.route('/meal-plan/<int:meal_plan_id>/to-shopping-list', methods=['POST'])
    @login_required
    def meal_plan_to_shopping_list(meal_plan_id):
        """Trasferisce ingredienti mancanti del meal plan nella lista spesa."""
        try:
            analysis = auto_update_shopping_from_meal_plan(current_user.id, meal_plan_id)
            if not analysis.get('success'):
                return jsonify({'success': False, 'message': analysis.get('message', 'Errore analisi')}), 400

            missing = analysis.get('missing_ingredients', [])
            if not missing:
                return jsonify({'success': True, 'updated': 0, 'message': 'Nessun ingrediente mancante'})

            shopping_list, updated_items = upsert_missing_ingredients_to_shopping_list(current_user.id, missing)
            return jsonify({'success': True, 'shopping_list_id': shopping_list.id, 'updated': len(updated_items), 'items': updated_items})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/meal-plan/<int:meal_plan_id>/consume', methods=['POST'])
    @login_required
    def meal_plan_consume(meal_plan_id):
        """Decrementa scorte in base agli ingredienti del MealPlan (consumo)."""
        try:
            analysis = auto_update_shopping_from_meal_plan(current_user.id, meal_plan_id)
            if not analysis.get('success'):
                return jsonify({'success': False, 'message': analysis.get('message', 'Errore analisi')}), 400

            available = analysis.get('already_available', [])
            # Decrementa solo quelli marcati come disponibili
            name_key_to_product = { p.name.strip().lower(): p for p in Product.query.filter_by(user_id=current_user.id, wasted=False).all() }
            decremented = []
            for ing in available:
                key = (ing.get('item') or '').strip().lower()
                qty = float(ing.get('quantity') or 0)
                unit = (ing.get('unit') or '').strip()
                prod = name_key_to_product.get(key)
                if prod and prod.unit == unit and qty > 0:
                    prod.quantity = max(0.0, (prod.quantity or 0) - qty)
                    decremented.append({'name': prod.name, 'quantity': qty, 'unit': unit})
            db.session.commit()
            return jsonify({'success': True, 'decremented': decremented})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500


    # ========================================
    # SISTEMA FAMIGLIA
    # ========================================
    
    @app.route('/family')
    @login_required
    def family():
        """Pagina gestione famiglia"""
        family = get_user_family(current_user.id)
        family_members = get_family_members(current_user.id) if family else []
        
        return render_template('family.html', family=family, family_members=family_members)
    
    
    @app.route('/family/create', methods=['POST'])
    @login_required
    def create_family_route():
        """Crea una nuova famiglia"""
        try:
            family_name = request.form.get('family_name', '').strip()
            
            if not family_name:
                return jsonify({'success': False, 'message': 'Nome famiglia obbligatorio'}), 400
            
            result = create_family(current_user.id, family_name)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': result['message'],
                    'family_code': result['family_code']
                })
            else:
                return jsonify({'success': False, 'message': result['message']}), 400
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Errore: {str(e)}'}), 500
    
    
    @app.route('/family/join', methods=['POST'])
    @login_required
    def join_family_route():
        """Unisciti a una famiglia tramite codice"""
        try:
            family_code = request.form.get('family_code', '').strip().upper()
            
            if not family_code:
                return jsonify({'success': False, 'message': 'Codice famiglia obbligatorio'}), 400
            
            result = join_family(current_user.id, family_code)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': result['message']
                })
            else:
                return jsonify({'success': False, 'message': result['message']}), 400
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Errore: {str(e)}'}), 500
    
    
    @app.route('/family/leave', methods=['POST'])
    @login_required
    def leave_family_route():
        """Lascia la famiglia"""
        try:
            result = leave_family(current_user.id)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': result['message']
                })
            else:
                return jsonify({'success': False, 'message': result['message']}), 400
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Errore: {str(e)}'}), 500
    
    
    @app.route('/family/members')
    @login_required
    def family_members():
        """API per ottenere membri della famiglia"""
        try:
            family = get_user_family(current_user.id)
            if not family:
                return jsonify({'success': False, 'message': 'Non sei membro di nessuna famiglia'}), 400
            
            members = get_family_members(current_user.id)
            members_data = []
            
            for member in members:
                members_data.append({
                    'id': member.user.id,
                    'username': member.user.username,
                    'email': member.user.email,
                    'is_admin': member.is_admin,
                    'joined_at': member.joined_at.isoformat()
                })
            
            return jsonify({
                'success': True,
                'family_name': family.name,
                'family_code': family.family_code,
                'members': members_data
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Errore: {str(e)}'}), 500


# ========================================
    # SPONSOR E PARTNERSHIP
    # ========================================
    
    @app.route('/sponsors')
    def sponsors():
        """Pagina sponsor e partnership"""
        return render_template('sponsors.html')
    
    
    @app.route('/meal-plan/<int:meal_id>', methods=['DELETE'])
    @login_required
    def delete_meal_plan(meal_id):
        """Elimina un pasto dal piano"""
        meal = MealPlan.query.get_or_404(meal_id)
        
        if meal.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Accesso negato'}), 403
        
        try:
            db.session.delete(meal)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Pasto eliminato con successo'})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Delete meal plan error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500