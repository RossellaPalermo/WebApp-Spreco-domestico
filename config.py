#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FoodFlow Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configurazione dell'applicazione."""
    # ===== SICUREZZA =====
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # ===== DATABASE =====
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:root@localhost/food_waste_app?charset=utf8mb4'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pool di connessioni per performance migliori
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'max_overflow': 20
    }

    # ===== API KEYS =====
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')  # La chiave deve essere impostata come variabile d'ambiente

    # ===== SESSION =====
    PERMANENT_SESSION_LIFETIME = 604800  # 7 giorni in secondi
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # ===== UPLOAD (se necessario in futuro) =====
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max


# Export per compatibilità con il tuo codice esistente
config = {
    'default': Config,
    'development': Config,
    'production': Config
}