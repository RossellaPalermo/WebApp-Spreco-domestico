"""
FoodFlow Application Factory
Gestisce inizializzazione app Flask e tutte le estensioni
Database: MySQL/MariaDB
"""

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
import logging
from logging.handlers import RotatingFileHandler
import os
from dotenv import load_dotenv

# Carica variabili d'ambiente dal file .env
load_dotenv()

# ===== INIZIALIZZA ESTENSIONI =====
db = SQLAlchemy()
login_manager = LoginManager()


def create_app(config_name=None):
    """
    Factory function per creare l'applicazione Flask
    
    Args:
        config_name: Nome configurazione ('development', 'production', 'testing')
                     Se None, usa 'default'
    
    Returns:
        Flask app configurata
    """
    app = Flask(__name__)
    
    # ===== CONFIGURAZIONE =====
    if config_name is None:
        config_name = 'default'
    
    from config import config
    app.config.from_object(config.get(config_name, config['default']))
    
    # Validazione SECRET_KEY
    if not app.config.get('SECRET_KEY'):
        app.logger.warning('SECRET_KEY non configurata! Usando valore temporaneo (NON sicuro per produzione)')
        app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    
    # ===== LOGGING =====
    configure_logging(app)
    
    # ===== INIZIALIZZA ESTENSIONI =====
    db.init_app(app)
    
    # Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Effettua il login per accedere a questa pagina.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'  # Protezione sessione contro hijacking
    
    # User loader per Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))
    
    # ===== REGISTRA ROUTES =====
    from .routes import register_routes
    register_routes(app)
    
    # ===== CREA DATABASE =====
    with app.app_context():
        try:
            # Per MySQL: crea tabelle solo se non esistono
            db.create_all()
            app.logger.info('Database tables verified/created')
            
            # Inizializza dati base (badges)
            initialize_database(app)
            
        except Exception as e:
            app.logger.error(f'Database initialization error: {e}')
            app.logger.warning('Continuando senza inizializzazione DB. Verifica connessione MySQL.')
    
    # ===== LOG STARTUP =====
    app.logger.info(f'FoodFlow started in {config_name} mode')
    try:
        with app.app_context():
            engine = db.get_engine()
            engine_name = engine.name if hasattr(engine, 'name') else str(engine.url.drivername)
    except Exception as e:
        app.logger.warning(f'Could not determine database engine: {e}')
        engine_name = 'Unknown'
    app.logger.info(f'Database engine: {engine_name}')
    
    return app


def configure_logging(app):
    """Configura logging per l'applicazione"""
    
    # Livello log
    log_level = logging.INFO
    app.logger.setLevel(log_level)
    
    # Crea cartella logs se non esiste
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # File handler con rotazione
    file_handler = RotatingFileHandler(
        'logs/foodflow.log',
        maxBytes=10485760,  # 10MB
        backupCount=10,
        encoding='utf-8'  # Importante per caratteri speciali
    )
    
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    
    file_handler.setLevel(log_level)
    app.logger.addHandler(file_handler)
    
    app.logger.info('Logging configured')


def initialize_database(app):
    """Inizializza dati base nel database (badges)"""
    from .models import Badge
    
    # Crea badges di default se non esistono
    default_badges = [
        {
            'name': 'Benvenuto',
            'description': 'Hai completato la registrazione',
            'icon': 'bi-star-fill',
            'points_required': 0,
            'condition': 'registration'
        },
        {
            'name': 'Primo Passo',
            'description': 'Hai aggiunto il primo prodotto',
            'icon': 'bi-box-seam',
            'points_required': 10,
            'condition': 'first_product'
        },
        {
            'name': 'Eco-Warrior',
            'description': 'Hai ridotto gli sprechi del 50%',
            'icon': 'bi-leaf',
            'points_required': 100,
            'condition': 'waste_reduction_50'
        },
        {
            'name': 'Chef Esperto',
            'description': 'Hai creato 10 ricette',
            'icon': 'bi-egg-fried',
            'points_required': 200,
            'condition': 'recipes_10'
        },
        {
            'name': 'Shopping Master',
            'description': 'Hai completato 5 liste spesa',
            'icon': 'bi-cart-check-fill',
            'points_required': 50,
            'condition': 'shopping_lists_5'
        },
        {
            'name': 'Nutrizionista',
            'description': 'Hai seguito il piano nutrizionale per 30 giorni',
            'icon': 'bi-heart-pulse-fill',
            'points_required': 300,
            'condition': 'nutrition_30_days'
        },
        {
            'name': 'Riciclatore',
            'description': 'Hai riciclato il primo prodotto',
            'icon': 'bi-recycle',
            'points_required': 10,
            'condition': 'first_recycle'
        },
        {
            'name': 'Eco-Hero',
            'description': 'Hai riciclato 10 prodotti',
            'icon': 'bi-leaf-fill',
            'points_required': 100,
            'condition': 'recycle_10'
        },
        {
            'name': 'Amico dell\'Ambiente',
            'description': 'Hai riciclato 25 prodotti',
            'icon': 'bi-globe',
            'points_required': 250,
            'condition': 'recycle_25'
        }
    ]
    
    try:
        badges_created = 0
        for badge_data in default_badges:
            # Controlla se badge esiste già
            existing = Badge.query.filter_by(name=badge_data['name']).first()
            if not existing:
                badge = Badge(**badge_data)
                db.session.add(badge)
                badges_created += 1
        
        if badges_created > 0:
            db.session.commit()
            app.logger.info(f'Initialized {badges_created} new badges')
        else:
            app.logger.info('All badges already exist')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error initializing badges: {e}')