// Minimal client config placeholder to avoid 404s and allow future overrides
window.FOODFLOW_CONFIG = window.FOODFLOW_CONFIG || {
    environment: 'production',
    version: '1.0.0'
};

// Expose a no-op init hook for optional per-page setup
window.initFoodFlow = window.initFoodFlow || function initFoodFlow() {};


