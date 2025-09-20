// Progress tracking for file processing jobs

class ProgressTracker {
    constructor() {
        this.activeJobs = new Map();
        this.pollInterval = 2000; // Poll every 2 seconds
        this.maxRetries = 3;
        this.isPolling = false;
        
        this.init();
    }
    
    init() {
        this.jobsList = document.getElementById('jobsList');
        
        // Start polling if there are existing jobs on page load
        this.checkForExistingJobs();
    }
    
    checkForExistingJobs() {
        // Check if there are any jobs in processing state on page load
        const processingJobs = document.querySelectorAll('[data-job-status="processing"], [data-job-status="pending"]');
        if (processingJobs.length > 0) {
            processingJobs.forEach(jobElement => {
                const jobId = jobElement.dataset.jobId;
                if (jobId) {
                    this.addJob(jobId, 0);
                }
            });
        }
    }
    
    addJob(jobId, retryCount = 0) {
        this.activeJobs.set(jobId, {
            id: jobId,
            retryCount: retryCount,
            lastUpdate: Date.now()
        });
        
        this.startPolling();
        this.createJobElement(jobId);
    }
    
    addJobs(jobIds) {
        jobIds.forEach(jobId => this.addJob(jobId));
    }
    
    removeJob(jobId) {
        this.activeJobs.delete(jobId);
        
        // Stop polling if no active jobs
        if (this.activeJobs.size === 0) {
            this.stopPolling();
        }
        
        this.removeJobElement(jobId);
    }
    
    createJobElement(jobId) {
        if (!this.jobsList) {
            console.error('jobsList element not found!');
            return;
        }
        
        const jobElement = document.createElement('div');
        jobElement.id = `job-${jobId}`;
        jobElement.className = 'bg-gray-50 rounded-lg p-4 border border-gray-200';
        jobElement.innerHTML = `
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                    <div>
                        <p class="text-sm font-medium text-gray-900">Processing...</p>
                        <p class="text-xs text-gray-500">Job ID: ${jobId}</p>
                    </div>
                </div>
                <div class="text-right">
                    <div class="text-sm text-gray-600">
                        <span id="progress-${jobId}">Initializing...</span>
                    </div>
                    <div class="mt-1">
                        <div class="w-32 bg-gray-200 rounded-full h-2">
                            <div id="progress-bar-${jobId}" class="bg-blue-600 h-2 rounded-full transition-all duration-300" style="width: 0%"></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.jobsList.appendChild(jobElement);
        
        // Show the active jobs section
        const activeJobsSection = document.getElementById('activeJobs');
        if (activeJobsSection) {
            activeJobsSection.classList.remove('hidden');
        }
    }
    
    updateJobElement(jobId, jobData) {
        console.log(`Updating job ${jobId} with status: ${jobData.status}`);
        const jobElement = document.getElementById(`job-${jobId}`);
        if (!jobElement) {
            console.warn(`Job element not found for job ${jobId}`);
            return;
        }
        
        const progressText = document.getElementById(`progress-${jobId}`);
        const progressBar = document.getElementById(`progress-bar-${jobId}`);
        
        if (jobData.status === 'completed') {
            // Job completed successfully
            const compressionRatio = jobData.compression_ratio ? Math.round((1 - jobData.compression_ratio) * 100) : 0;
            
            jobElement.innerHTML = `
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <div class="rounded-full h-6 w-6 bg-green-100 flex items-center justify-center">
                            <svg class="h-4 w-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                            </svg>
                        </div>
                        <div>
                            <p class="text-sm font-medium text-gray-900">${jobData.original_filename || 'File'}</p>
                            <p class="text-xs text-gray-500">
                                Compressed by ${compressionRatio}% • 
                                ${Utils.formatFileSize(jobData.original_size)} → ${Utils.formatFileSize(jobData.processed_size)}
                            </p>
                        </div>
                    </div>
                    <div class="flex space-x-2">
                        <a href="/api/process/download/${jobId}" 
                           class="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500">
                            Download
                        </a>
                        <button onclick="window.ProgressTracker.removeJob('${jobId}')"
                                class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500">
                            Dismiss
                        </button>
                    </div>
                </div>
            `;
            
            // Remove from active jobs after a delay
            setTimeout(() => {
                this.removeJob(jobId);
            }, 30000); // Remove after 30 seconds
            
            // Refresh the recent files section to show the completed job
            this.refreshRecentFiles();
            
        } else if (jobData.status === 'failed') {
            // Job failed
            jobElement.innerHTML = `
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <div class="rounded-full h-6 w-6 bg-red-100 flex items-center justify-center">
                            <svg class="h-4 w-4 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </div>
                        <div>
                            <p class="text-sm font-medium text-gray-900">Processing Failed</p>
                            <p class="text-xs text-red-500">${jobData.error_message || 'Unknown error occurred'}</p>
                        </div>
                    </div>
                    <button onclick="window.ProgressTracker.removeJob('${jobId}')"
                            class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500">
                        Dismiss
                    </button>
                </div>
            `;
            
            // Refresh the recent files section to show the failed job
            this.refreshRecentFiles();
            
        } else {
            // Job still processing
            const progress = jobData.progress || 0;
            const timeRemaining = jobData.time_remaining || 'Calculating...';
            
            if (progressText) {
                progressText.textContent = `${progress}% • ${timeRemaining} remaining`;
            }
            
            if (progressBar) {
                progressBar.style.width = `${progress}%`;
            }
        }
    }
    
    removeJobElement(jobId) {
        const jobElement = document.getElementById(`job-${jobId}`);
        if (jobElement) {
            jobElement.remove();
        }
        
        // Hide active jobs section if no jobs
        if (this.jobsList && this.jobsList.children.length === 0) {
            const activeJobsSection = document.getElementById('activeJobs');
            if (activeJobsSection) {
                activeJobsSection.classList.add('hidden');
            }
        }
    }
    
    startPolling() {
        if (this.isPolling) {
            console.log('Polling already active');
            return;
        }
        
        console.log(`Starting polling for ${this.activeJobs.size} jobs`);
        this.isPolling = true;
        this.pollJobs();
    }
    
    stopPolling() {
        this.isPolling = false;
    }
    
    async pollJobs() {
        if (!this.isPolling || this.activeJobs.size === 0) {
            this.isPolling = false;
            return;
        }
        
        try {
            // Poll each active job
            const pollPromises = Array.from(this.activeJobs.keys()).map(async (jobId) => {
                try {
                    const jobData = await API.getJobStatus(jobId);
                    this.updateJobElement(jobId, jobData);
                    
                    // Remove completed or failed jobs from active list
                    if (jobData.status === 'completed' || jobData.status === 'failed' || jobData.status === 'expired') {
                        // Remove from active tracking immediately
                        this.activeJobs.delete(jobId);
                        console.log(`Job ${jobId} ${jobData.status}, removed from active tracking`);
                    }
                    
                    // Reset retry count on successful poll
                    const job = this.activeJobs.get(jobId);
                    if (job) {
                        job.retryCount = 0;
                        job.lastUpdate = Date.now();
                    }
                    
                } catch (error) {
                    console.error(`Failed to poll job ${jobId}:`, error);
                    
                    // Handle retry logic
                    const job = this.activeJobs.get(jobId);
                    if (job) {
                        job.retryCount = (job.retryCount || 0) + 1;
                        
                        if (job.retryCount >= this.maxRetries) {
                            console.error(`Max retries reached for job ${jobId}, removing from tracking`);
                            this.removeJob(jobId);
                        }
                    }
                }
            });
            
            await Promise.allSettled(pollPromises);
            
        } catch (error) {
            console.error('Polling error:', error);
        }
        
        // Schedule next poll
        if (this.isPolling && this.activeJobs.size > 0) {
            setTimeout(() => {
                this.pollJobs();
            }, this.pollInterval);
        } else {
            this.isPolling = false;
        }
    }
    
    async refreshJob(jobId) {
        // Manually refresh a specific job's status
        console.log(`Manually refreshing job ${jobId}`);
        try {
            const jobData = await API.getJobStatus(jobId);
            this.updateJobElement(jobId, jobData);
            
            // If completed, remove from active list
            if (jobData.status === 'completed' || jobData.status === 'failed' || jobData.status === 'expired') {
                this.activeJobs.delete(jobId);
                console.log(`Job ${jobId} ${jobData.status}, removed from active tracking`);
                
                // Refresh recent files
                this.refreshRecentFiles();
            }
        } catch (error) {
            console.error(`Failed to refresh job ${jobId}:`, error);
        }
    }
    
    async refreshRecentFiles() {
        // Refresh the recent files section with updated data
        try {
            const response = await fetch('/api/recent-jobs');
            const data = await response.json();
            
            if (!data.success) {
                console.error('Failed to fetch recent jobs:', data.message);
                return;
            }
            
            const recentFilesSection = document.querySelector('.flow-root ul[role="list"]');
            if (!recentFilesSection) {
                return;
            }
            
            // Clear existing items
            recentFilesSection.innerHTML = '';
            
            // Add updated jobs
            data.jobs.forEach(job => {
                const listItem = this.createRecentFileItem(job);
                recentFilesSection.appendChild(listItem);
            });
            
        } catch (error) {
            console.error('Error refreshing recent files:', error);
        }
    }
    
    createRecentFileItem(job) {
        // Create a list item for the recent files section
        const li = document.createElement('li');
        li.className = 'py-3';
        
        const statusBadge = this.getStatusBadge(job.status);
        const downloadButton = job.status === 'completed' ? 
            `<a href="/download/${job.id}" class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-md text-blue-600 bg-blue-100 hover:bg-blue-200">
                Download
            </a>` : '';
        
        li.innerHTML = `
            <div class="flex items-center justify-between">
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-900 truncate">
                        ${job.original_filename}
                    </p>
                    <p class="text-xs text-gray-500">
                        ${new Date(job.created_at).toLocaleDateString()} • 
                        ${Utils.formatFileSize(job.original_size)}
                        ${job.compression_ratio ? ` • Compressed by ${Math.round((1 - job.compression_ratio) * 100)}%` : ''}
                    </p>
                </div>
                <div class="flex items-center space-x-2">
                    ${statusBadge}
                    ${downloadButton}
                </div>
            </div>
        `;
        
        return li;
    }
    
    getStatusBadge(status) {
        // Get HTML for status badge based on job status
        const badges = {
            'completed': '<span class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">Completed</span>',
            'processing': '<span class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">Processing</span>',
            'pending': '<span class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800">Pending</span>',
            'failed': '<span class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800">Failed</span>',
            'expired': '<span class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800">Expired</span>'
        };
        return badges[status] || badges['pending'];
    }
}

// Note: ProgressTracker initialization is handled in the dashboard template  
// to ensure proper loading order
