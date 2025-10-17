"""
FoodFlow Database Models
Ottimizzato per MySQL/MariaDB con HeidiSQL
"""

from flask_login import UserMixin
from datetime import datetime
from . import db

# ========================================
# UTENTI E AUTENTICAZIONE
# ========================================

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)  # 255 per bcrypt
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Relazioni (lazy='dynamic' per query efficienti)
    products = db.relationship('Product', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    shopping_lists = db.relationship('ShoppingList', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    user_stats = db.relationship('UserStats', backref='user', uselist=False, cascade='all, delete-orphan')
    user_badges = db.relationship('UserBadge', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    nutritional_profile = db.relationship('NutritionalProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    nutritional_goals = db.relationship('NutritionalGoal', backref='user', uselist=False, cascade='all, delete-orphan')
    meal_plans = db.relationship('MealPlan', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    daily_nutrition = db.relationship('DailyNutrition', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    waste_analytics = db.relationship('WasteAnalytics', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    shopping_analytics = db.relationship('ShoppingAnalytics', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reward_history = db.relationship('RewardHistory', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    # Relazioni famiglia
    family_memberships = db.relationship('FamilyMember', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'


# ========================================
# SISTEMA FAMIGLIA
# ========================================

class Family(db.Model):
    __tablename__ = 'family'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    family_code = db.Column(db.String(12), unique=True, nullable=False, index=True)  # Codice di 12 caratteri
    created_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    # Relazioni
    members = db.relationship('FamilyMember', backref='family', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Family {self.name} ({self.family_code})>'
    
    @property
    def member_count(self):
        """Numero di membri della famiglia"""
        return self.members.count()
    
    @property
    def admin_user(self):
        """Utente amministratore della famiglia"""
        return User.query.get(self.created_by)


class FamilyMember(db.Model):
    __tablename__ = 'family_member'
    
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    joined_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    is_admin = db.Column(db.Boolean, default=False)
    
    # Constraint per evitare duplicati
    __table_args__ = (
        db.UniqueConstraint('family_id', 'user_id', name='unique_family_member'),
    )
    
    def __repr__(self):
        return f'<FamilyMember family_id={self.family_id} user_id={self.user_id}>'


# ========================================
# DISPENSA
# ========================================

class Product(db.Model):
    __tablename__ = 'product'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    min_quantity = db.Column(db.Float, default=1.0)
    wasted = db.Column(db.Boolean, default=False, index=True)
    is_shared = db.Column(db.Boolean, default=False, index=True)  # Indica se il prodotto è condiviso in famiglia
    allergens = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    def __repr__(self):
        return f'<Product {self.name}>'
    
    @property
    def is_expiring_soon(self, days=7):
        """Controlla se il prodotto scade nei prossimi N giorni"""
        from datetime import timedelta
        return self.expiry_date <= datetime.now().date() + timedelta(days=days)
    
    @property
    def is_low_stock(self):
        """Controlla se il prodotto è sotto scorta minima"""
        return self.quantity <= self.min_quantity


# ========================================
# SHOPPING LIST
# ========================================

class ShoppingList(db.Model):
    __tablename__ = 'shopping_list'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    store_name = db.Column(db.String(100), nullable=True)
    budget = db.Column(db.Float, nullable=True)
    actual_spent = db.Column(db.Float, default=0.0)
    completed = db.Column(db.Boolean, default=False, index=True)
    is_smart = db.Column(db.Boolean, default=False)
    is_template = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relazioni
    items = db.relationship('ShoppingItem', backref='shopping_list', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ShoppingList {self.name}>'
    
    @property
    def total_items(self):
        """Numero totale items"""
        return self.items.count()
    
    @property
    def completed_items(self):
        """Numero items completati"""
        return self.items.filter_by(completed=True).count()
    
    @property
    def progress_percentage(self):
        """Percentuale completamento"""
        total = self.total_items
        if total == 0:
            return 0
        return round((self.completed_items / total) * 100, 1)
    
    @property
    def estimated_total(self):
        """Costo totale stimato"""
        return sum(item.estimated_price or 0 for item in self.items)
    
    @property
    def is_over_budget(self):
        """Controlla se ha superato il budget"""
        if not self.budget:
            return False
        return self.actual_spent > self.budget
    
    def to_dict(self):
        """Serializza per JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'store_name': self.store_name,
            'budget': self.budget,
            'actual_spent': self.actual_spent,
            'completed': self.completed,
            'is_smart': self.is_smart,
            'total_items': self.total_items,
            'completed_items': self.completed_items,
            'progress_percentage': self.progress_percentage,
            'estimated_total': self.estimated_total,
            'is_over_budget': self.is_over_budget,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ShoppingItem(db.Model):
    __tablename__ = 'shopping_item'
    
    id = db.Column(db.Integer, primary_key=True)
    shopping_list_id = db.Column(db.Integer, db.ForeignKey('shopping_list.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=True, index=True)
    completed = db.Column(db.Boolean, default=False, index=True)
    priority = db.Column(db.Integer, default=0)  # 0=normale, 1=media, 2=alta
    estimated_price = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    def __repr__(self):
        return f'<ShoppingItem {self.name}>'
    
    def to_dict(self):
        """Serializza per JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'quantity': self.quantity,
            'unit': self.unit,
            'category': self.category,
            'completed': self.completed,
            'priority': self.priority,
            'estimated_price': self.estimated_price,
            'notes': self.notes
        }


# ========================================
# GAMIFICATION
# ========================================

class UserStats(db.Model):
    __tablename__ = 'user_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    total_products_added = db.Column(db.Integer, default=0)
    total_products_wasted = db.Column(db.Integer, default=0)
    total_shopping_lists = db.Column(db.Integer, default=0)
    total_recipes_created = db.Column(db.Integer, default=0)
    goals_achieved = db.Column(db.Integer, default=0)
    waste_reduction_score = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    def __repr__(self):
        return f'<UserStats user_id={self.user_id} points={self.points}>'


class Badge(db.Model):
    __tablename__ = 'badge'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    points_required = db.Column(db.Integer, default=0)
    condition = db.Column(db.String(100))
    category = db.Column(db.String(50), nullable=False, default='general')
    
    def __repr__(self):
        return f'<Badge {self.name}>'


class UserBadge(db.Model):
    __tablename__ = 'user_badge'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id', ondelete='CASCADE'), nullable=False, index=True)
    earned_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Constraint per evitare badge duplicati per utente
    __table_args__ = (
        db.UniqueConstraint('user_id', 'badge_id', name='unique_user_badge'),
    )
    
    def __repr__(self):
        return f'<UserBadge user_id={self.user_id} badge_id={self.badge_id}>'


class RewardHistory(db.Model):
    __tablename__ = 'reward_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    reward_type = db.Column(db.String(50), nullable=False)  # "points" o "badge"
    value = db.Column(db.Integer, default=0)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id', ondelete='SET NULL'), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), index=True)
    
    # Relazione con Badge
    badge = db.relationship('Badge', backref='reward_history')
    
    def __repr__(self):
        return f'<RewardHistory {self.reward_type} +{self.value}>'


# ========================================
# PIANO NUTRIZIONALE
# ========================================

class NutritionalProfile(db.Model):
    __tablename__ = 'nutritional_profile'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    age = db.Column(db.Integer, nullable=True)
    weight = db.Column(db.Float, nullable=True)  # kg
    height = db.Column(db.Float, nullable=True)  # cm
    gender = db.Column(db.String(10), default='male')
    activity_level = db.Column(db.String(20), default='moderate')
    goal = db.Column(db.String(20), default='maintain')
    dietary_restrictions = db.Column(db.Text, nullable=True)  # JSON string
    allergies = db.Column(db.Text, nullable=True)  # JSON string
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    def __repr__(self):
        return f'<NutritionalProfile user_id={self.user_id}>'


class NutritionalGoal(db.Model):
    __tablename__ = 'nutritional_goal'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    daily_calories = db.Column(db.Float, nullable=False)
    daily_protein = db.Column(db.Float, nullable=False)
    daily_carbs = db.Column(db.Float, nullable=False)
    daily_fat = db.Column(db.Float, nullable=False)
    daily_fiber = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())
    
    def __repr__(self):
        return f'<NutritionalGoal user_id={self.user_id} calories={self.daily_calories}>'


class MealPlan(db.Model):
    __tablename__ = 'meal_plan'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    custom_meal = db.Column(db.Text, nullable=True)
    is_shared = db.Column(db.Boolean, default=False, index=True)  # Indica se il pasto è condiviso in famiglia
    calories = db.Column(db.Float, nullable=True)
    protein = db.Column(db.Float, nullable=True)
    carbs = db.Column(db.Float, nullable=True)
    fat = db.Column(db.Float, nullable=True)
    fiber = db.Column(db.Float, nullable=True)
    servings = db.Column(db.Integer, default=2)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Indice composito per query efficienti
    __table_args__ = (
        db.Index('idx_user_date', 'user_id', 'date'),
    )
    
    def __repr__(self):
        return f'<MealPlan {self.date} {self.meal_type}>'


class DailyNutrition(db.Model):
    __tablename__ = 'daily_nutrition'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    calories_consumed = db.Column(db.Float, default=0.0)
    protein_consumed = db.Column(db.Float, default=0.0)
    carbs_consumed = db.Column(db.Float, default=0.0)
    fat_consumed = db.Column(db.Float, default=0.0)
    fiber_consumed = db.Column(db.Float, default=0.0)
    calories_goal = db.Column(db.Float, default=2000.0)
    protein_goal = db.Column(db.Float, default=150.0)
    carbs_goal = db.Column(db.Float, default=250.0)
    fat_goal = db.Column(db.Float, default=65.0)
    fiber_goal = db.Column(db.Float, default=25.0)
    goal_completion_percentage = db.Column(db.Float, default=0.0)
    consistency_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Constraint per evitare duplicati giornalieri
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_daily_nutrition'),
        db.Index('idx_user_date_nutrition', 'user_id', 'date'),
    )
    
    def __repr__(self):
        return f'<DailyNutrition {self.date} {self.calories_consumed}cal>'


# ========================================
# ANALYTICS
# ========================================

class WasteAnalytics(db.Model):
    __tablename__ = 'waste_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    products_wasted = db.Column(db.Integer, default=0)
    kg_wasted = db.Column(db.Float, default=0.0)
    estimated_cost = db.Column(db.Float, default=0.0)
    category_breakdown = db.Column(db.Text, nullable=True)  # JSON string
    waste_trend = db.Column(db.Float, default=0.0)
    most_wasted_category = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Indice composito
    __table_args__ = (
        db.Index('idx_user_date_waste', 'user_id', 'date'),
    )
    
    def __repr__(self):
        return f'<WasteAnalytics {self.date} {self.kg_wasted}kg>'


class ShoppingAnalytics(db.Model):
    __tablename__ = 'shopping_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    items_purchased = db.Column(db.Integer, default=0)
    estimated_cost = db.Column(db.Float, default=0.0)
    category_breakdown = db.Column(db.Text, nullable=True)  # JSON string
    ai_suggestions_used = db.Column(db.Integer, default=0)
    most_purchased_category = db.Column(db.String(50), nullable=True)
    shopping_frequency_days = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    
    # Indice composito
    __table_args__ = (
        db.Index('idx_user_date_shopping', 'user_id', 'date'),
    )
    
    def __repr__(self):
        return f'<ShoppingAnalytics {self.date} {self.items_purchased} items>'