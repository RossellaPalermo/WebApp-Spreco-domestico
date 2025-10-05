"""
FoodFlow Routes
Gestisce tutte le routes dell'applicazione
"""

import re
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from sqlalchemy import func

from . import db
from .models import (
    User, Product, ShoppingList, ShoppingItem, UserStats,
    Badge, UserBadge, NutritionalProfile,
    NutritionalGoal, MealPlan
)

from .smart_functions import (
    get_expiring_products, get_low_stock_products,
    award_points, calculate_waste_reduction_score,
    calculate_nutritional_goals, smart_notification_system,
    auto_update_shopping_from_meal_plan, upsert_missing_ingredients_to_shopping_list
)

from .ai_functions import (
    suggest_recipes,
    ai_optimize_meal_planning,
    ai_suggest_shopping_list,
    ai_generate_recipe_suggestions
)

from .analytics import get_comprehensive_analytics


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
            expiring_products = get_expiring_products(current_user.id)
            low_stock_products = get_low_stock_products(current_user.id)
            
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
            
            analytics = get_comprehensive_analytics(current_user.id, days=30)
            smart_notifications = smart_notification_system(current_user.id)
            shopping_lists = ShoppingList.query.filter_by(user_id=current_user.id).limit(5).all()
            
            return render_template(
                'dashboard_modern.html',
                expiring_products=expiring_products,
                low_stock_products=low_stock_products,
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
            return render_template('dashboard_modern.html')
    
    
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
                db.session.flush()
                
                # Crea stats iniziali
                stats = UserStats(user_id=user.id)
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
        """Lista prodotti dispensa"""
        products = Product.query.filter_by(
            user_id=current_user.id,
            wasted=False
        ).order_by(Product.expiry_date.asc()).all()
        
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
                    allergens=request.form.get('allergens', '').strip(),
                    notes=request.form.get('notes', '').strip()
                )
                
                db.session.add(product)
                db.session.commit()
                
                # Gamification
                award_points(current_user.id, 'product_added', 10)
                
                # Aggiorna stats
                stats = UserStats.query.filter_by(user_id=current_user.id).first()
                if stats:
                    stats.total_products_added += 1
                    db.session.commit()
                
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
                product.expiry_date = datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date()
                product.category = request.form['category']
                product.min_quantity = float(request.form.get('min_quantity', 1))
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
            
            flash('Prodotto eliminato con successo', 'success')
            return jsonify({'success': True})
            
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
            
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    
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
        
        # Arricchisci con statistiche
        for lst in lists:
            lst.total_items = lst.items.count()
            lst.completed_items = lst.items.filter_by(completed=True).count()
            lst.completion_percentage = (lst.completed_items / lst.total_items * 100) if lst.total_items > 0 else 0
        
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
            
            return jsonify({
                'success': True,
                'message': f'Lista "{name}" creata!',
                'list_id': shopping_list.id
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
        
        return render_template('gamification.html', stats=stats, badges=badges)
    
    
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

                profile.dietary_restrictions = _to_json_array_string(request.form.get('dietary_restrictions', ''))
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
                meal_plan = MealPlan(
                    user_id=current_user.id,
                    date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
                    meal_type=request.form.get('meal_type', 'lunch'),
                    custom_meal=request.form.get('custom_meal', '')
                )
                
                db.session.add(meal_plan)
                db.session.commit()
                
                flash('Piano pasti creato!', 'success')
                return redirect(url_for('meal_planning'))
                
            except Exception as e:
                db.session.rollback()
                flash('Errore nella creazione', 'danger')
        
        profile = NutritionalProfile.query.filter_by(user_id=current_user.id).first()
        goals = NutritionalGoal.query.filter_by(user_id=current_user.id).first()
        meal_plans = MealPlan.query.filter_by(user_id=current_user.id).order_by(MealPlan.date.desc()).all()
        
        return render_template(
            'meal_planning.html',
            nutritional_profile=profile,
            nutritional_goals=goals,
            meal_plans=meal_plans,
            today=datetime.now().date()
        )
    
    
    # ========================================
    # ANALYTICS
    # ========================================
    
    @app.route('/analytics')
    @login_required
    def analytics():
        """Pagina analytics"""
        analytics_data = get_comprehensive_analytics(current_user.id, days=30)
        return render_template('analytics.html', analytics=analytics_data)
    
    
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