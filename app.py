#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FoodFlow Application Entry Point
"""

import os
from app import create_app

# Crea l'applicazione
app = create_app()

if __name__ == '__main__':
    # Configurazione da variabili d'ambiente con fallback
    debug_mode = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    
    app.run(
        debug=debug_mode,
        host=host,
        port=port,
        use_reloader=debug_mode
    )