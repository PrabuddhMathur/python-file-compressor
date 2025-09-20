// Main JavaScript functionality for PDF Compressor

// CSRF Token handling
function getCSRFToken() {
    const token = document.querySelector('meta[name=csrf-token]').getAttribute('content');
    return token === 'disabled' ? null : token;
}

// Global AJAX setup for CSRF
document.addEventListener('DOMContentLoaded', function() {
    // Set up CSRF token for all AJAX requests
    const csrfToken = getCSRFToken();
    if (csrfToken) {
        // For jQuery if available
        if (typeof $ !== 'undefined') {
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                        xhr.setRequestHeader("X-CSRFToken", csrfToken);
                    }
                }
            });
        }
    }
});

// Utility functions
const Utils = {
    // Format file size in human readable format
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    // Show notification
    showNotification: function(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 p-4 rounded-md shadow-lg z-50 ${this.getNotificationClasses(type)}`;
        notification.innerHTML = `
            <div class="flex items-center">
                <div class="ml-3">
                    <p class="text-sm font-medium">${message}</p>
                </div>
                <div class="ml-4 flex-shrink-0">
                    <button class="inline-flex text-gray-400 hover:text-gray-600 focus:outline-none" onclick="this.parentNode.parentNode.parentNode.remove()">
                        <svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                        </svg>
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, duration);
        }
    },
    
    // Get notification CSS classes based on type
    getNotificationClasses: function(type) {
        const classes = {
            'success': 'bg-green-100 border border-green-400 text-green-700',
            'error': 'bg-red-100 border border-red-400 text-red-700',
            'warning': 'bg-yellow-100 border border-yellow-400 text-yellow-700',
            'info': 'bg-blue-100 border border-blue-400 text-blue-700'
        };
        return classes[type] || classes['info'];
    },
    
    // Debounce function
    debounce: function(func, wait, immediate) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func(...args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func(...args);
        };
    }
};

// API helpers
const API = {
    // Make authenticated API request
    request: function(url, options = {}) {
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            credentials: 'same-origin'
        };
        
        const config = { ...defaults, ...options };
        if (config.headers && options.headers) {
            config.headers = { ...defaults.headers, ...options.headers };
        }
        
        return fetch(url, config)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .catch(error => {
                console.error('API request failed:', error);
                Utils.showNotification('Request failed: ' + error.message, 'error');
                throw error;
            });
    },
    
    // Get user quota information
    getUserQuota: function() {
        return this.request('/api/user/quota');
    },
    
    // Clear session files
    clearSession: function() {
        return this.request('/api/user/clear-session', { method: 'POST' });
    },
    
    // Get job status
    getJobStatus: function(jobId) {
        return this.request(`/api/process/status/${jobId}`);
    }
};

// Form validation helpers
const FormValidator = {
    // Validate email format
    isValidEmail: function(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },
    
    // Validate password strength
    isValidPassword: function(password) {
        return password.length >= 8 && /[A-Za-z]/.test(password) && /[0-9]/.test(password);
    },
    
    // Validate PDF file
    isValidPDF: function(file) {
        return file && file.type === 'application/pdf' && file.size <= 25 * 1024 * 1024; // 25MB
    },
    
    // Show field error
    showFieldError: function(fieldId, message) {
        const field = document.getElementById(fieldId);
        if (!field) return;
        
        // Remove existing error
        this.clearFieldError(fieldId);
        
        // Add error styling
        field.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
        
        // Add error message
        const errorDiv = document.createElement('div');
        errorDiv.id = `${fieldId}-error`;
        errorDiv.className = 'mt-1 text-sm text-red-600';
        errorDiv.textContent = message;
        field.parentNode.appendChild(errorDiv);
    },
    
    // Clear field error
    clearFieldError: function(fieldId) {
        const field = document.getElementById(fieldId);
        if (!field) return;
        
        // Remove error styling
        field.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
        
        // Remove error message
        const errorDiv = document.getElementById(`${fieldId}-error`);
        if (errorDiv) {
            errorDiv.remove();
        }
    }
};

// Export for use in other scripts
window.Utils = Utils;
window.API = API;
window.FormValidator = FormValidator;
