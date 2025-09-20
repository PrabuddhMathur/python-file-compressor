// File upload handling with drag & drop support

class FileUploader {
    constructor() {
        this.dropArea = document.getElementById('dropArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadForm = document.getElementById('uploadForm');
        this.uploadButton = document.getElementById('uploadButton');
        this.selectedFiles = [];
        this.isUploading = false;  // Add upload state flag
        
        this.init();
    }
    
    init() {
        if (!this.dropArea || !this.fileInput || !this.uploadForm) {
            console.warn('Upload elements not found on this page');
            return;
        }
        
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.dropArea.addEventListener(eventName, this.preventDefaults.bind(this), false);
            document.body.addEventListener(eventName, this.preventDefaults.bind(this), false);
        });
        
        // Highlight drop area when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            this.dropArea.addEventListener(eventName, this.highlight.bind(this), false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            this.dropArea.addEventListener(eventName, this.unhighlight.bind(this), false);
        });
        
        // Handle dropped files
        this.dropArea.addEventListener('drop', this.handleDrop.bind(this), false);
        
        // Handle file input change
        this.fileInput.addEventListener('change', this.handleFileSelect.bind(this), false);
        
        // Handle form submission
        this.uploadForm.addEventListener('submit', this.handleSubmit.bind(this), false);
        
        // Handle file input click
        this.dropArea.addEventListener('click', () => {
            this.fileInput.click();
        });
    }
    
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    highlight() {
        this.dropArea.classList.add('drag-over');
    }
    
    unhighlight() {
        this.dropArea.classList.remove('drag-over');
    }
    
    handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        this.handleFiles(files);
    }
    
    handleFileSelect(e) {
        const files = e.target.files;
        this.handleFiles(files);
    }
    
    handleFiles(files) {
        this.selectedFiles = [];
        
        // Validate and process each file
        Array.from(files).forEach(file => {
            if (this.validateFile(file)) {
                this.selectedFiles.push(file);
            }
        });
        
        if (this.selectedFiles.length > 0) {
            this.updateUI();
            this.enableUpload();
        } else {
            this.disableUpload();
        }
    }
    
    validateFile(file) {
        // Check if it's a PDF
        if (!file.type || file.type !== 'application/pdf') {
            Utils.showNotification(`${file.name} is not a PDF file`, 'error');
            return false;
        }
        
        // Check file size (25MB limit)
        const maxSize = 25 * 1024 * 1024; // 25MB in bytes
        if (file.size > maxSize) {
            Utils.showNotification(`${file.name} is too large. Maximum size is 25MB`, 'error');
            return false;
        }
        
        return true;
    }
    
    updateUI() {
        if (this.selectedFiles.length === 0) {
            return;
        }
        
        let filesList = '';
        let totalSize = 0;
        
        this.selectedFiles.forEach(file => {
            totalSize += file.size;
            filesList += `<div class="flex items-center justify-between p-2 bg-gray-50 rounded">
                <span class="text-sm text-gray-700">${file.name}</span>
                <span class="text-xs text-gray-500">${Utils.formatFileSize(file.size)}</span>
            </div>`;
        });
        
        const filesInfo = `
            <div class="mt-4 p-4 bg-blue-50 rounded-lg">
                <h4 class="text-sm font-medium text-blue-800 mb-2">
                    ${this.selectedFiles.length} file(s) selected (${Utils.formatFileSize(totalSize)} total)
                </h4>
                <div class="space-y-2">
                    ${filesList}
                </div>
            </div>
        `;
        
        // Update drop area content
        const existingInfo = this.dropArea.querySelector('.files-info');
        if (existingInfo) {
            existingInfo.remove();
        }
        
        const infoDiv = document.createElement('div');
        infoDiv.className = 'files-info';
        infoDiv.innerHTML = filesInfo;
        this.dropArea.appendChild(infoDiv);
        
        // Enable upload button
        this.enableUpload();
        
        // Call global form ready check if available
        if (window.checkFormReady) {
            window.checkFormReady();
        }
    }
    
    enableUpload() {
        if (this.uploadButton) {
            this.uploadButton.disabled = false;
            const fileCount = this.selectedFiles.length;
            if (fileCount === 1) {
                this.uploadButton.textContent = 'Upload and Compress';
            } else {
                this.uploadButton.textContent = `Upload and Compress ${fileCount} files`;
            }
        }
    }
    
    disableUpload() {
        if (this.uploadButton) {
            this.uploadButton.disabled = true;
            this.uploadButton.textContent = 'Upload and Compress';
        }
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        // Prevent double submission
        if (this.isUploading) {
            Utils.showNotification('Upload already in progress', 'warning');
            return;
        }
        
        if (this.selectedFiles.length === 0) {
            Utils.showNotification('Please select a PDF file', 'error');
            return;
        }
        
        // Get selected quality from radio buttons
        const qualityRadio = this.uploadForm.querySelector('input[name="quality"]:checked');
        if (!qualityRadio) {
            Utils.showNotification('Please select a quality level', 'error');
            return;
        }
        
        const quality = qualityRadio.value;
        
        // Set uploading state
        this.isUploading = true;
        
        // Disable the form during upload
        this.setFormDisabled(true);
        
        try {
            const totalFiles = this.selectedFiles.length;
            let successCount = 0;
            let failedCount = 0;
            const failedFiles = [];
            
            // Update button to show progress
            this.updateUploadProgress(0, totalFiles);
            
            // Upload all files sequentially
            for (let i = 0; i < this.selectedFiles.length; i++) {
                const file = this.selectedFiles[i];
                
                try {
                    const result = await this.uploadFile(file, quality);
                    
                    if (result && result.success && result.job && result.job.id) {
                        successCount++;
                    } else {
                        failedCount++;
                        failedFiles.push(file.name);
                    }
                } catch (error) {
                    console.error(`Upload error for ${file.name}:`, error);
                    failedCount++;
                    failedFiles.push(file.name);
                }
                
                // Update progress
                this.updateUploadProgress(i + 1, totalFiles);
            }
            
            // Show consolidated success message
            if (successCount > 0 && failedCount === 0) {
                // All files uploaded successfully
                const message = totalFiles === 1 
                    ? `Successfully uploaded 1 file for processing`
                    : `Done uploading ${successCount} files for processing`;
                Utils.showNotification(message, 'success');
            } else if (successCount > 0 && failedCount > 0) {
                // Some files failed
                const message = `Uploaded ${successCount} files successfully, ${failedCount} failed`;
                Utils.showNotification(message, 'warning');
            } else {
                // All files failed
                const message = totalFiles === 1 
                    ? 'Upload failed'
                    : `All ${totalFiles} uploads failed`;
                Utils.showNotification(message, 'error');
            }
            
            // Redirect to history page to see the processing status
            if (successCount > 0) {
                setTimeout(() => {
                    window.location.href = '/history';
                }, 1500);
            }
            
        } catch (error) {
            console.error('Upload error:', error);
            Utils.showNotification('Upload failed: ' + error.message, 'error');
        } finally {
            // Reset uploading state
            this.isUploading = false;
            this.setFormDisabled(false);
            this.resetForm();
        }
    }
    
    async uploadFile(file, quality) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('quality', quality);
        
        const headers = {};
        const csrfToken = getCSRFToken();
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
        
        const response = await fetch('/api/process/upload', {
            method: 'POST',
            body: formData,
            headers: headers
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || `Upload failed: ${response.status}`);
        }
        
        return await response.json();
    }
    
    monitorJobs(jobIds) {
        // Initialize progress tracking for uploaded jobs
        if (window.ProgressTracker) {
            window.ProgressTracker.addJobs(jobIds);
        }
    }
    
    updateUploadProgress(current, total) {
        if (total === 1) {
            // Single file - show simple uploading message
            this.uploadButton.innerHTML = `
                <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Uploading...
            `;
        } else {
            // Multiple files - show progress
            this.uploadButton.innerHTML = `
                <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Uploading ${current}/${total}...
            `;
        }
    }

    setFormDisabled(disabled) {
        const inputs = this.uploadForm.querySelectorAll('input, button');
        inputs.forEach(input => {
            input.disabled = disabled;
        });
        
        if (!disabled) {
            this.uploadButton.innerHTML = 'Upload and Compress';
        }
        // Note: When disabled=true, the button text is set by updateUploadProgress()
    }
    
    resetForm() {
        this.selectedFiles = [];
        this.fileInput.value = '';
        
        // Reset drop area
        const filesInfo = this.dropArea.querySelector('.files-info');
        if (filesInfo) {
            filesInfo.remove();
        }
        
        this.disableUpload();
    }
}

// Note: FileUploader initialization is handled in the dashboard template
// to ensure proper loading order
