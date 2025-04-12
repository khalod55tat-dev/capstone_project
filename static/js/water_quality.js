// Water Quality Monitoring JavaScript

class WaterQualityMonitor {
    constructor() {
        this.loadingState = null;
        this.resultsSection = null;
        this.errorMessage = null;
        this.interpretationSection = null;
        
        // Initialize after DOM is loaded
        this.initialize();
    }
    
    initialize() {
        // Initialize DOM elements
        this.loadingState = document.getElementById('loadingState');
        this.resultsSection = document.getElementById('resultsSection');
        this.errorMessage = document.getElementById('errorMessage');
        this.interpretationSection = document.getElementById('interpretationSection');
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Initial data fetch
        this.updateData();
        
        // Set up periodic updates
        setInterval(() => this.updateData(), 300000); // Update every 5 minutes
    }
    
    showLoading() {
        if (this.loadingState && this.loadingState.style) {
            this.loadingState.style.display = 'block';
        }
    }
    
    hideLoading() {
        if (this.loadingState && this.loadingState.style) {
            this.loadingState.style.display = 'none';
        }
    }
    
    showError(message) {
        if (this.errorMessage && this.errorMessage.style) {
            this.errorMessage.textContent = message;
            this.errorMessage.style.display = 'block';
        }
    }
    
    hideError() {
        if (this.errorMessage && this.errorMessage.style) {
            this.errorMessage.style.display = 'none';
        }
    }
    
    showResults() {
        if (this.resultsSection && this.resultsSection.style) {
            this.resultsSection.style.display = 'block';
        }
    }
    
    hideResults() {
        if (this.resultsSection && this.resultsSection.style) {
            this.resultsSection.style.display = 'none';
        }
    }
    
    setupEventListeners() {
        const sendReportBtn = document.getElementById('sendReportBtn');
        if (sendReportBtn) {
            sendReportBtn.addEventListener('click', () => this.sendReport());
        }
    }
    
    async updateData() {
        try {
            this.showLoading();
            this.hideError();
            
            const response = await fetch('/get_latest_data');
            const data = await response.json();
            
            if (data.success) {
                this.updateUI(data.data);
            } else {
                this.showError(data.message || 'Failed to fetch data');
            }
        } catch (error) {
            console.error('Error fetching data:', error);
            this.showError('Failed to connect to server');
        } finally {
            this.hideLoading();
        }
    }
    
    updateUI(data) {
        if (!data) {
            this.showError('No data available');
            return;
        }
        
        // Update parameter values
        this.updateElement('phValue', data.ph?.toFixed(2) || 'N/A');
        this.updateElement('tdsValue', data.tds?.toFixed(2) || 'N/A');
        this.updateElement('turbidityValue', data.turbidity?.toFixed(2) || 'N/A');
        this.updateElement('wqiValue', data.wqi_formula?.toFixed(2) || 'N/A');
        
        // Update visualization
        const plotImage = document.getElementById('plotImage');
        if (plotImage && data.plot_image) {
            plotImage.src = `data:image/png;base64,${data.plot_image}`;
            plotImage.style.display = 'block';
        }
        
        // Update interpretation
        if (data.interpretation) {
            this.updateInterpretation(data.interpretation);
        }
        
        // Update timestamp
        this.updateElement('timestamp', new Date().toLocaleString());
        
        this.showResults();
    }
    
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }
    
    updateInterpretation(interpretation) {
        const analysisReport = document.getElementById('analysisReport');
        if (!analysisReport) return;
        
        if (!interpretation || !interpretation.overall) {
            analysisReport.innerHTML = '<div class="alert alert-warning">No interpretation available</div>';
            return;
        }
        
        try {
            // Get the current language from the user's settings
            const currentLang = document.documentElement.lang || 'en';
            
            analysisReport.innerHTML = `
                <div class="alert alert-info">
                    <h6>${currentLang === 'en' ? 'Overall Water Quality' : 
                         currentLang === 'te' ? 'మొత్తం నీటి నాణ్యత' : 
                         currentLang === 'ta' ? 'மொத்த நீர் தரம்' : 'Overall Water Quality'}: 
                        ${interpretation.overall.grade || 'N/A'}</h6>
                    <p>${interpretation.overall.message || 'No message available'}</p>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4">
                        <div class="alert alert-secondary">
                            <h6>${currentLang === 'en' ? 'pH Level' : 
                                 currentLang === 'te' ? 'pH స్థాయి' : 
                                 currentLang === 'ta' ? 'pH நிலை' : 'pH Level'}: 
                                ${interpretation.ph?.grade || 'N/A'}</h6>
                            <p>${interpretation.ph?.message || 'No message available'}</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="alert alert-secondary">
                            <h6>${currentLang === 'en' ? 'TDS Level' : 
                                 currentLang === 'te' ? 'TDS స్థాయి' : 
                                 currentLang === 'ta' ? 'TDS நிலை' : 'TDS Level'}: 
                                ${interpretation.tds?.grade || 'N/A'}</h6>
                            <p>${interpretation.tds?.message || 'No message available'}</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="alert alert-secondary">
                            <h6>${currentLang === 'en' ? 'Turbidity' : 
                                 currentLang === 'te' ? 'మసక' : 
                                 currentLang === 'ta' ? 'கலங்கல்' : 'Turbidity'}: 
                                ${interpretation.turbidity?.grade || 'N/A'}</h6>
                            <p>${interpretation.turbidity?.message || 'No message available'}</p>
                        </div>
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Error updating interpretation:', error);
            analysisReport.innerHTML = '<div class="alert alert-danger">Error displaying interpretation data</div>';
        }
    }
    
    async sendReport() {
        try {
            const response = await fetch('/get_latest_data');
            const data = await response.json();
            
            if (data.success) {
                const reportData = {
                    ph: data.data.ph,
                    tds: data.data.tds,
                    turbidity: data.data.turbidity,
                    wqi: data.data.wqi_formula
                };
                
                const sendResponse = await fetch('/send_report', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(reportData)
                });
                
                const result = await sendResponse.json();
                if (result.status === 'success') {
                    alert('Report sent successfully!');
                } else {
                    alert('Error sending report: ' + result.message);
                }
            }
        } catch (error) {
            console.error('Error sending report:', error);
            alert('Error sending report: ' + error.message);
        }
    }
}

// Initialize the monitor when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new WaterQualityMonitor();
}); 