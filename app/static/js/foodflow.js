/* ===== FOODFLOW - JAVASCRIPT ESSENZIALE ===== */

// ===== UTILITY FUNCTIONS =====
const FoodFlow = {
    // Mostra notifica toast
    showNotification: function(type, message, duration = 5000) {
        const iconMap = {
            'success': 'bi-check-circle-fill',
            'danger': 'bi-exclamation-triangle-fill',
            'warning': 'bi-exclamation-circle-fill',
            'info': 'bi-info-circle-fill'
        };
        
        const notification = document.createElement('div');
        notification.className = `toast align-items-center text-bg-${type} border-0 position-fixed bottom-0 end-0 m-3`;
        notification.setAttribute('role', 'alert');
        notification.style.zIndex = '9999';
        notification.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi ${iconMap[type] || iconMap.info} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        document.body.appendChild(notification);
        const toast = new bootstrap.Toast(notification, { delay: duration });
        toast.show();
        
        // Rimuovi dal DOM dopo la chiusura
        notification.addEventListener('hidden.bs.toast', () => notification.remove());
    },
    
    // Imposta stato loading su button
    setButtonLoading: function(button, loading = true) {
        if (loading) {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Caricamento...';
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.innerHTML;
        }
    },
    
    // Formatta data in italiano
    formatDate: function(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('it-IT', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    },
    
    // Formatta valuta in Euro
    formatCurrency: function(amount) {
        return new Intl.NumberFormat('it-IT', {
            style: 'currency',
            currency: 'EUR'
        }).format(amount);
    },
    
    // Debounce per ottimizzare ricerche
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    },
    
    // Conferma azione (per delete, etc.)
    confirmAction: function(message, callback) {
        if (confirm(message)) {
            callback();
        }
    }
};

// ===== MODAL HELPER =====
const ModalManager = {
    show: function(modalId, data = {}) {
        const modalEl = document.getElementById(modalId);
        if (!modalEl) return;
        
        // Popola campi modal con data
        Object.entries(data).forEach(([key, value]) => {
            const field = modalEl.querySelector(`[data-field="${key}"]`);
            if (field) {
                if (field.tagName === 'INPUT' || field.tagName === 'TEXTAREA') {
                    field.value = value;
                } else {
                    field.textContent = value;
                }
            }
        });
        
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    },
    
    hide: function(modalId) {
        const modalEl = document.getElementById(modalId);
        if (!modalEl) return;
        
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    }
};

// ===== API HELPER =====
const API = {
    async call(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            FoodFlow.showNotification('danger', `Errore: ${error.message}`);
            throw error;
        }
    },
    
    get(url) {
        return this.call(url);
    },
    
    post(url, data) {
        return this.call(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    
    delete(url) {
        return this.call(url, { method: 'DELETE' });
    }
};

// ===== INIZIALIZZAZIONE AL CARICAMENTO =====
document.addEventListener('DOMContentLoaded', function() {
    
    // 1. Inizializza tooltip Bootstrap
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
        new bootstrap.Tooltip(el);
    });
    
    // 2. Inizializza popover Bootstrap
    document.querySelectorAll('[data-bs-toggle="popover"]').forEach(el => {
        new bootstrap.Popover(el);
    });
    
    // 3. Loading automatico sui form submit
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                FoodFlow.setButtonLoading(submitBtn, true);
            }
        });
    });
    
    // 4. Conferma su azioni pericolose
    document.querySelectorAll('[data-confirm]').forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.dataset.confirm || 'Sei sicuro?';
            if (!confirm(message)) {
                e.preventDefault();
                e.stopPropagation();
            }
        });
    });
    
    // 5. Auto-hide degli alert dopo 5 secondi
    setTimeout(() => {
        document.querySelectorAll('.alert:not(.alert-permanent)').forEach(alert => {
            const bsAlert = bootstrap.Alert.getInstance(alert);
            if (bsAlert) bsAlert.close();
        });
    }, 5000);
    
    // 6. Navbar scroll effect
    const navbar = document.getElementById('mainNavbar');
    if (navbar) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }
    
    // 7. Inizializza AOS (animazioni scroll)
    if (typeof AOS !== 'undefined') {
        AOS.init({
            duration: 800,
            easing: 'ease-in-out',
            once: true,
            offset: 100
        });
    }
    
    // 8. Card hover effects
    document.querySelectorAll('.card').forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-8px)';
            this.style.transition = 'all 0.3s ease';
        });
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
});

// ===== TOGGLE COLLAPSE (per dashboard cards) =====
function toggleCollapse(btn, contentId) {
    const content = document.getElementById(contentId);
    const icon = btn.querySelector('i');
    
    if (!content) return;
    
    if (content.style.display === 'none') {
        content.style.display = '';
        icon.classList.remove('bi-chevron-up');
        icon.classList.add('bi-chevron-down');
    } else {
        content.style.display = 'none';
        icon.classList.remove('bi-chevron-down');
        icon.classList.add('bi-chevron-up');
    }
}

// ===== ESPORTA GLOBALMENTE =====
window.FoodFlow = FoodFlow;
window.ModalManager = ModalManager;
window.API = API;
window.toggleCollapse = toggleCollapse;