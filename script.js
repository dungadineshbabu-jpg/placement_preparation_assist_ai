/**
 * Placement Preparation Assistant
 * Custom JavaScript - All pages
 * Version: 2.0
 */

document.addEventListener('DOMContentLoaded', function() {

    // ========== TOGGLE PASSWORD VISIBILITY ==========
    document.querySelectorAll('.toggle-password').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var target = document.getElementById(this.dataset.target);
            var icon = this.querySelector('i');
            if (target) {
                if (target.type === 'password') {
                    target.type = 'text';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                } else {
                    target.type = 'password';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
            }
        });
    });

    // ========== AUTO-DISMISS FLASH ALERTS ==========
    setTimeout(function() {
        document.querySelectorAll('.alert:not(.alert-permanent)').forEach(function(alert) {
            try {
                var bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } catch (e) {
                // Fallback: manual close
                alert.style.transition = 'opacity 0.5s';
                alert.style.opacity = '0';
                setTimeout(function() {
                    alert.style.display = 'none';
                }, 500);
            }
        });
    }, 5000);

    // ========== NAVBAR DROPDOWN CLOSE ON OUTSIDE CLICK ==========
    document.addEventListener('click', function(e) {
        var dropdowns = document.querySelectorAll('.dropdown-menu.show');
        dropdowns.forEach(function(menu) {
            if (!menu.closest('.dropdown')) {
                menu.classList.remove('show');
            }
        });
    });

    // ========== PREVENT DROPDOWN FROM CLOSING WHEN CLICKING INSIDE ==========
    document.querySelectorAll('.dropdown-menu').forEach(function(menu) {
        menu.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    });

    // ========== KEYBOARD SHORTCUTS ==========
    document.addEventListener('keydown', function(e) {
        // Ctrl+S = Save (if on forms)
        if (e.ctrlKey && e.key === 's') {
            var form = document.querySelector('form');
            var saveBtn = document.getElementById('saveResumeBtn');
            if (form && form.querySelector('[type="submit"]')) {
                e.preventDefault();
                form.querySelector('[type="submit"]').click();
            } else if (saveBtn) {
                e.preventDefault();
                saveBtn.click();
            }
        }

        // Escape = Close modals
        if (e.key === 'Escape') {
            var modals = document.querySelectorAll('.modal.show');
            modals.forEach(function(modal) {
                try {
                    var bsModal = bootstrap.Modal.getInstance(modal);
                    if (bsModal) bsModal.hide();
                } catch (err) {}
            });
        }
    });

    // ========== TOOLTIP INITIALIZATION (if Bootstrap tooltips are used) ==========
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // ========== POPOVER INITIALIZATION (if Bootstrap popovers are used) ==========
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // ========== CONFIRM DELETE ==========
    document.querySelectorAll('.confirm-delete').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            var message = this.dataset.message || 'Are you sure you want to delete this item?';
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
            return true;
        });
    });

    // ========== DYNAMIC WORD COUNTER (for textareas) ==========
    document.querySelectorAll('textarea[data-word-count]').forEach(function(textarea) {
        var counterId = textarea.dataset.wordCount;
        var counterEl = document.getElementById(counterId);
        if (counterEl) {
            textarea.addEventListener('input', function() {
                var words = this.value.trim() ? this.value.trim().split(/\s+/).length : 0;
                counterEl.textContent = 'Words: ' + words;
            });
        }
    });

    // ========== DYNAMIC CHAR COUNTER (for textareas) ==========
    document.querySelectorAll('textarea[data-char-count]').forEach(function(textarea) {
        var counterId = textarea.dataset.charCount;
        var counterEl = document.getElementById(counterId);
        if (counterEl) {
            textarea.addEventListener('input', function() {
                counterEl.textContent = 'Characters: ' + this.value.length;
            });
        }
    });

    // ========== SMOOTH SCROLL FOR ANCHOR LINKS ==========
    document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
        anchor.addEventListener('click', function(e) {
            var href = this.getAttribute('href');
            if (href === '#') return;
            var target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // ========== DROPDOWN TOGGLE ON HOVER (Desktop only) ==========
    if (window.innerWidth >= 992) {
        document.querySelectorAll('.nav-item.dropdown').forEach(function(item) {
            item.addEventListener('mouseenter', function() {
                var menu = this.querySelector('.dropdown-menu');
                if (menu) {
                    // Close other dropdowns
                    document.querySelectorAll('.dropdown-menu.show').forEach(function(otherMenu) {
                        if (otherMenu !== menu) {
                            otherMenu.classList.remove('show');
                        }
                    });
                    menu.classList.add('show');
                }
            });
            item.addEventListener('mouseleave', function() {
                var menu = this.querySelector('.dropdown-menu');
                if (menu && !menu.matches(':hover')) {
                    // Don't close if it's a click-open (handled by document click)
                }
            });
        });
    }

    // ========== RESIZE HANDLER (reinitialize hover on resize) ==========
    var resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            // Handle any resize-specific logic here
            console.log('Window resized');
        }, 250);
    });

    console.log('✅ Placement Prep AI - JavaScript loaded successfully!');
});