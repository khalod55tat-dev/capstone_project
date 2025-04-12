from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from flask_migrate import Migrate
import numpy as np
import joblib
import requests
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Set the backend to 'Agg' before importing pyplot
import matplotlib.pyplot as plt
import seaborn as sns
import base64
from io import BytesIO
import time
from datetime import datetime, timedelta
from flask_login import login_user, login_required, current_user, LoginManager, UserMixin, logout_user
from flask_mail import Mail, Message
import google.generativeai as genai
from googletrans import Translator
import secrets
import string
import re  # Add at the top with other imports
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Use environment variable for secret key
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = '99220041968@klu.ac.in'
app.config['MAIL_PASSWORD'] = 'jdij wqcl gacl lcay'  # App Password
app.config['MAIL_DEFAULT_SENDER'] = ('KARE Healthcare', '99220041968@klu.ac.in')
app.config['ADMIN_EMAIL'] = '99220041968@klu.ac.in'
app.config['MAIL_DEBUG'] = True  # Enable debug mode for email
app.config['MAIL_SUPPRESS_SEND'] = False

# Initialize Flask-Mail
mail = Mail(app)

# Translator initialization
translator = Translator()

# Database configuration
if os.getenv('DATABASE_URL'):
    # Production Database (Render PostgreSQL)
    database_url = os.getenv('DATABASE_URL')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local SQLite Database
    basedir = os.path.abspath(os.path.dirname(__file__))
    database_path = os.path.join(basedir, 'users.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'

print(f"Using database at: {app.config['SQLALCHEMY_DATABASE_URI']}")  # Debug print
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Flask extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# User model
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    data_source = db.Column(db.String(20), default='thingspeak')  # 'thingspeak' or 'blink'
    # ThingSpeak configuration
    thingspeak_channel_id = db.Column(db.String(50))
    thingspeak_read_api_key = db.Column(db.String(50))
    # Blink configuration
    blink_auth_token = db.Column(db.String(100))
    blink_device_id = db.Column(db.String(50))
    password_reset_attempts = db.Column(db.Integer, default=0, nullable=True)
    last_password_reset = db.Column(db.DateTime, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    preferred_language = db.Column(db.String(10), default='en')
    verification_token = db.Column(db.String(32))
    email_verified = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def increment_reset_attempts(self):
        if self.password_reset_attempts is None:
            self.password_reset_attempts = 0
        self.password_reset_attempts += 1
        self.last_password_reset = datetime.utcnow()
        db.session.commit()
    
    def reset_password_attempts(self):
        self.password_reset_attempts = 0
        self.last_password_reset = None
        db.session.commit()
    
    def is_password_reset_locked(self):
        if not self.last_password_reset or self.password_reset_attempts is None:
            return False
        # Lock for 15 minutes if 5 failed attempts
        if self.password_reset_attempts >= 5:
            lockout_duration = timedelta(minutes=15)
            if datetime.utcnow() - self.last_password_reset < lockout_duration:
                return True
            else:
                # Reset attempts if lockout period has passed
                self.reset_password_attempts()
                return False
        return False

class WQIConfig(db.Model):
    __tablename__ = 'wqi_config'  # Explicitly set table name
    id = db.Column(db.Integer, primary_key=True)
    parameter = db.Column(db.String(50), nullable=False)
    min_value = db.Column(db.Float, nullable=False)
    max_value = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Update foreign key to match new table name
    
    def __repr__(self):
        return f'<WQIConfig {self.parameter}>'

def init_default_config():
    with app.app_context():
        if not WQIConfig.query.first():
            default_configs = [
                WQIConfig(parameter='ph_normal', min_value=7.0, max_value=8.0, weight=0.4),
                WQIConfig(parameter='ph_acidic', min_value=6.5, max_value=7.0, weight=0.5),
                WQIConfig(parameter='ph_alkaline', min_value=8.0, max_value=8.5, weight=0.5),
                WQIConfig(parameter='tds_normal', min_value=0, max_value=500, weight=0.3),
                WQIConfig(parameter='tds_high', min_value=500, max_value=1000, weight=0.4),
                WQIConfig(parameter='turbidity_normal', min_value=0, max_value=1, weight=0.3),
                WQIConfig(parameter='turbidity_high', min_value=1, max_value=5, weight=0.4)
            ]
            for config in default_configs:
                db.session.add(config)
            db.session.commit()

def get_current_config():
    configs = WQIConfig.query.all()
    config_dict = {}
    for config in configs:
        config_dict[config.parameter] = {
            'min_value': config.min_value,
            'max_value': config.max_value,
            'weight': config.weight
        }
    return config_dict

def calculate_wqi(ph, tds, turbidity):
    configs = get_current_config()
    
    # Calculate individual parameter scores with dynamic ranges
    def get_ph_score(ph):
        if ph < configs['ph_acidic']['min_value'] or ph > configs['ph_alkaline']['max_value']:
            return 0
        elif configs['ph_normal']['min_value'] <= ph <= configs['ph_normal']['max_value']:
            return 100
        else:
            return 80

    def get_tds_score(tds):
        if tds > configs['tds_high']['max_value']:
            return 0
        elif tds <= configs['tds_normal']['max_value']:
            return 100
        else:
            return 80 - ((tds - configs['tds_normal']['max_value']) * 0.1)

    def get_turbidity_score(turbidity):
        if turbidity > configs['turbidity_high']['max_value']:
            return 0
        elif turbidity <= configs['turbidity_normal']['max_value']:
            return 100
        else:
            return 80 - ((turbidity - configs['turbidity_normal']['max_value']) * 20)

    # Calculate scores
    ph_score = get_ph_score(ph)
    tds_score = get_tds_score(tds)
    turbidity_score = get_turbidity_score(turbidity)

    # Determine weights based on conditions using dynamic config
    if ph < configs['ph_acidic']['min_value'] or ph > configs['ph_alkaline']['max_value']:
        weights = {
            'ph': configs['ph_acidic']['weight'],
            'tds': configs['tds_normal']['weight'],
            'turbidity': configs['turbidity_normal']['weight']
        }
    elif tds > configs['tds_high']['max_value']:
        weights = {
            'ph': configs['ph_normal']['weight'],
            'tds': configs['tds_high']['weight'],
            'turbidity': configs['turbidity_normal']['weight']
        }
    elif turbidity > configs['turbidity_high']['max_value']:
        weights = {
            'ph': configs['ph_normal']['weight'],
            'tds': configs['tds_normal']['weight'],
            'turbidity': configs['turbidity_high']['weight']
        }
    else:
        weights = {
            'ph': configs['ph_normal']['weight'],
            'tds': configs['tds_normal']['weight'],
            'turbidity': configs['turbidity_normal']['weight']
        }

    # Calculate WQI
    wqi = (
        ph_score * weights['ph'] +
        tds_score * weights['tds'] +
        turbidity_score * weights['turbidity']
    )

    return wqi

def get_wqi_grade(wqi):
    if wqi >= 80:
        return 'A'
    elif wqi >= 60:
        return 'B'
    else:
        return 'C'

def get_water_quality_interpretation(ph, tds, turbidity, wqi):
    """Generate a detailed interpretation of water quality parameters."""
    messages = []
    
    # pH interpretation
    if 6.5 <= ph <= 8.5:
        if 7.0 <= ph <= 8.0:
            messages.append("pH is in the optimal range for drinking water.")
        else:
            messages.append("pH is acceptable but not optimal.")
    else:
        if ph < 6.5:
            messages.append("Water is too acidic and may be corrosive.")
        else:
            messages.append("Water is too alkaline and may taste bitter.")
    
    # TDS interpretation
    if tds <= 300:
        messages.append("TDS level is excellent.")
    elif tds <= 500:
        messages.append("TDS level is good for drinking water.")
    elif tds <= 1000:
        messages.append("TDS level is acceptable but not ideal.")
    else:
        messages.append("TDS level is too high and water may taste unpleasant.")
    
    # Turbidity interpretation
    if turbidity <= 1:
        messages.append("Turbidity is excellent, water is very clear.")
    elif turbidity <= 5:
        messages.append("Turbidity is acceptable for drinking water.")
    else:
        messages.append("Turbidity is too high, water appears cloudy.")
    
    # Overall WQI interpretation
    if wqi >= 80:
        messages.append("Overall water quality is excellent and safe for drinking.")
    elif wqi >= 60:
        messages.append("Water quality is acceptable but could be improved.")
    else:
        messages.append("Water quality is poor and may not be safe for drinking without treatment.")
    
    return " ".join(messages)

def create_visualization(ph, tds, turbidity, wqi_formula, wqi_predicted):
    try:
        # Create figure with a light background
        plt.clf()  # Clear any existing plots
        fig = plt.figure(figsize=(12, 8), facecolor='white')
        
        # Create subplots with adjusted layout
        gs = plt.GridSpec(2, 2, figure=fig)
        
        # Parameter values plot
        ax1 = fig.add_subplot(gs[0, 0])
        params = ['pH', 'TDS (mg/L)', 'Turbidity (NTU)']
        values = [ph, tds, turbidity]
        colors = ['#17a2b8', '#28a745', '#ffc107']
        
        bars = ax1.bar(params, values, color=colors)
        ax1.set_title('Current Parameter Values', pad=15, fontsize=12, fontweight='bold')
        ax1.set_ylim(0, max(values) * 1.2)
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}', ha='center', va='bottom')
        
        # WQI Comparison
        ax2 = fig.add_subplot(gs[0, 1])
        wqi_values = [wqi_formula, wqi_predicted]
        wqi_labels = ['Formula WQI', 'ML Model WQI']
        
        bars = ax2.bar(wqi_labels, wqi_values, color=['#007bff', '#6f42c1'])
        ax2.set_title('WQI Comparison', pad=15, fontsize=12, fontweight='bold')
        ax2.set_ylim(0, 100)
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}', ha='center', va='bottom')
        
        # Parameter ranges plot
        ax3 = fig.add_subplot(gs[1, :])
        
        # Define ideal ranges with colors
        ranges = {
            'pH': {'range': (6.5, 8.5), 'optimal': (7.0, 8.0)},
            'TDS (mg/L)': {'range': (0, 1000), 'optimal': (0, 500)},
            'Turbidity (NTU)': {'range': (0, 5), 'optimal': (0, 1)}
        }
        
        current_values = {
            'pH': ph,
            'TDS (mg/L)': tds,
            'Turbidity (NTU)': turbidity
        }
        
        y_pos = np.arange(len(ranges))
        
        # Plot ranges with optimal zones
        for i, (param, range_data) in enumerate(ranges.items()):
            # Plot acceptable range
            full_range = range_data['range']
            ax3.barh(i, full_range[1] - full_range[0], left=full_range[0], 
                    color='#e9ecef', height=0.3, alpha=0.5)
            
            # Plot optimal range
            optimal = range_data['optimal']
            ax3.barh(i, optimal[1] - optimal[0], left=optimal[0],
                    color='#28a745', height=0.3, alpha=0.3)
            
            # Plot current value with color based on range
            current_val = current_values[param]
            color = '#28a745' if optimal[0] <= current_val <= optimal[1] else (
                '#ffc107' if full_range[0] <= current_val <= full_range[1] else '#dc3545')
            ax3.plot(current_val, i, 'o', color=color, markersize=10)
            
            # Add value label
            ax3.text(current_val, i, f' {current_val:.2f}', 
                    va='center', ha='left' if current_val < full_range[1]/2 else 'right')
        
        ax3.set_yticks(y_pos)
        ax3.set_yticklabels(ranges.keys())
        ax3.set_title('Parameter Ranges Analysis', pad=15, fontsize=12, fontweight='bold')
        
        # Add legend for range plot
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#28a745', alpha=0.3, label='Optimal Range'),
            Patch(facecolor='#e9ecef', alpha=0.5, label='Acceptable Range'),
            plt.Line2D([0], [0], marker='o', color='#28a745', label='Good',
                      markerfacecolor='#28a745', markersize=8, linestyle=''),
            plt.Line2D([0], [0], marker='o', color='#ffc107', label='Acceptable',
                      markerfacecolor='#ffc107', markersize=8, linestyle=''),
            plt.Line2D([0], [0], marker='o', color='#dc3545', label='Poor',
                      markerfacecolor='#dc3545', markersize=8, linestyle='')
        ]
        ax3.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1, 0.5))
        
        # Adjust layout
        plt.tight_layout()
        
        # Convert plot to base64 string
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_png = buffer.getvalue()
        buffer.close()
        plt.close(fig)  # Explicitly close the figure
        
        return base64.b64encode(image_png).decode('utf-8')
    except Exception as e:
        print(f"Error creating visualization: {e}")
        return None

def fetch_thingspeak_data(user):
    try:
        # Use user's ThingSpeak credentials if available, otherwise use defaults
        channel_id = user.thingspeak_channel_id or THINGSPEAK_CHANNEL_ID
        read_api_key = user.thingspeak_read_api_key or THINGSPEAK_READ_API_KEY
        
        print(f"Fetching data for user {user.username}")
        print(f"Using Channel ID: {channel_id}")
        print(f"Using API Key: {read_api_key}")
        
        if not channel_id or not read_api_key:
            print("No ThingSpeak credentials found")
            return None
            
        url = f"https://api.thingspeak.com/channels/{channel_id}/feeds/last.json"
        print(f"Fetching data from ThingSpeak URL: {url}")
        
        # Add timeout to prevent hanging requests
        response = requests.get(url, params={'api_key': read_api_key}, timeout=10)
        print(f"ThingSpeak API response status: {response.status_code}")
        print(f"ThingSpeak API response text: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Received ThingSpeak data: {data}")
            
            # Validate data fields
            if not all(key in data for key in ['field1', 'field2', 'field3']):
                print("Missing required fields in ThingSpeak data")
                return None
                
            try:
                return {
                    'ph': float(data['field1']),
                    'tds': float(data['field2']),
                    'turbidity': float(data['field3']),
                    'timestamp': data['created_at']
                }
            except (ValueError, TypeError) as e:
                print(f"Error converting ThingSpeak data: {e}")
                return None
        else:
            print(f"ThingSpeak API error: {response.status_code} - {response.text}")
            return None
    except requests.Timeout:
        print("ThingSpeak API request timed out")
        return None
    except requests.RequestException as e:
        print(f"ThingSpeak API request error: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"Error parsing ThingSpeak data: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching ThingSpeak data: {e}")
        return None

# Routes
@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)

@app.route('/water_quality')
@login_required
def water_quality():
    return render_template('water_quality.html', 
                         loading=True,
                         prediction_made=False)

@app.route('/get_latest_data')
@login_required
def get_latest_data():
    try:
        # Get user's preferred language
        user_lang = current_user.preferred_language if current_user else 'en'
        
        # Fetch data from ThingSpeak
        thingspeak_data = fetch_thingspeak_data(current_user)
        if not thingspeak_data:
            return jsonify({'success': False, 'message': 'Failed to fetch data from ThingSpeak'})

        # Extract values
        ph = float(thingspeak_data['ph'])
        tds = float(thingspeak_data['tds'])
        turbidity = float(thingspeak_data['turbidity'])

        # Calculate WQI
        wqi_formula = calculate_wqi(ph, tds, turbidity)
        wqi_predicted = wqi_formula  # Using formula value for now

        # Create visualization
        plot_image = create_visualization(ph, tds, turbidity, wqi_formula, wqi_predicted)

        # Generate interpretations with translations
        interpretation = {
            "ph": get_ph_interpretation(ph, user_lang),
            "tds": get_tds_interpretation(tds, user_lang),
            "turbidity": get_turbidity_interpretation(turbidity, user_lang),
            "overall": get_overall_interpretation(wqi_formula, user_lang)
        }

        # Prepare response data
        response_data = {
            'success': True,
            'data': {
                'ph': ph,
                'tds': tds,
                'turbidity': turbidity,
                'wqi_formula': wqi_formula,
                'wqi_predicted': wqi_predicted,
                'plot_image': plot_image,
                'timestamp': thingspeak_data['timestamp'],
                'interpretation': interpretation
            }
        }

        return jsonify(response_data)
    except Exception as e:
        print(f"Error in get_latest_data: {e}")
        return jsonify({'success': False, 'message': str(e)})

def get_ph_interpretation(ph, language='en'):
    if 7.0 <= ph <= 8.0:
        message = "pH is in the optimal range for drinking water."
        suggestions = "No action required. Continue regular monitoring."
        precautions = "Maintain current water treatment practices."
    elif 6.5 <= ph <= 8.5:
        message = "pH is acceptable but not optimal for drinking water."
        suggestions = "Consider adjusting water treatment to bring pH closer to neutral."
        precautions = "Monitor pH levels more frequently."
    elif ph < 6.5:
        message = "Water is too acidic and may be corrosive. Not recommended for drinking."
        suggestions = "Add alkaline substances to neutralize acidity. Consider installing a pH correction system."
        precautions = "Avoid using acidic water for cooking or drinking. Check for corrosion in pipes."
    else:
        message = "Water is too alkaline and may taste bitter. Not recommended for drinking."
        suggestions = "Add acid neutralizers or install a pH correction system."
        precautions = "Avoid using alkaline water for cooking or drinking. Check for scale buildup in pipes."
    
    # Translate all components
    translated_message = translate_text(message, language)
    translated_suggestions = translate_text(suggestions, language)
    translated_precautions = translate_text(precautions, language)
    
    return {
        "grade": "A" if 7.0 <= ph <= 8.0 else "B" if 6.5 <= ph <= 8.5 else "C",
        "message": translated_message,
        "suggestions": translated_suggestions,
        "precautions": translated_precautions
    }

def get_tds_interpretation(tds, language='en'):
    if tds <= 300:
        message = "TDS level is excellent, indicating very pure water."
        suggestions = "No action required. Continue regular monitoring."
        precautions = "Maintain current water treatment practices."
    elif tds <= 500:
        message = "TDS level is acceptable for drinking water but monitoring is recommended."
        suggestions = "Consider installing a reverse osmosis system if TDS continues to rise."
        precautions = "Monitor TDS levels regularly. Check for potential contamination sources."
    else:
        message = "TDS level is too high. Water may taste unpleasant and contain harmful minerals."
        suggestions = "Install a reverse osmosis system or water softener. Consider alternative water sources."
        precautions = "Avoid drinking water with high TDS. Check for potential industrial contamination."
    
    # Translate all components
    translated_message = translate_text(message, language)
    translated_suggestions = translate_text(suggestions, language)
    translated_precautions = translate_text(precautions, language)
    
    return {
        "grade": "A" if tds <= 300 else "B" if tds <= 500 else "C",
        "message": translated_message,
        "suggestions": translated_suggestions,
        "precautions": translated_precautions
    }

def get_turbidity_interpretation(turbidity, language='en'):
    if turbidity <= 1:
        message = "Water is very clear with excellent turbidity levels."
        suggestions = "No action required. Continue regular monitoring."
        precautions = "Maintain current water treatment practices."
    elif turbidity <= 5:
        message = "Turbidity is acceptable but water clarity could be improved."
        suggestions = "Consider installing or upgrading filtration systems."
        precautions = "Monitor turbidity levels regularly. Check for potential contamination sources."
    else:
        message = "Water is too cloudy and requires treatment before consumption."
        suggestions = "Install or upgrade filtration systems. Consider using coagulation treatment."
        precautions = "Do not drink cloudy water. Boil water before use. Check for potential contamination sources."
    
    # Translate all components
    translated_message = translate_text(message, language)
    translated_suggestions = translate_text(suggestions, language)
    translated_precautions = translate_text(precautions, language)
    
    return {
        "grade": "A" if turbidity <= 1 else "B" if turbidity <= 5 else "C",
        "message": translated_message,
        "suggestions": translated_suggestions,
        "precautions": translated_precautions
    }

def get_overall_interpretation(wqi, language='en'):
    if wqi >= 80:
        message = "Water quality is excellent and safe for drinking."
        suggestions = "Continue current water treatment practices. Regular monitoring is sufficient."
        precautions = "Maintain existing water treatment systems. Regular testing is recommended."
    elif wqi >= 60:
        message = "Water quality is acceptable but regular monitoring is recommended."
        suggestions = "Consider upgrading water treatment systems. Implement regular testing schedule."
        precautions = "Monitor water quality parameters more frequently. Check treatment systems regularly."
    else:
        message = "Water quality is poor. Treatment is required before consumption."
        suggestions = "Immediate action required. Install comprehensive water treatment system. Consider alternative water sources."
        precautions = "Do not consume untreated water. Boil water before use. Regular testing is essential."
    
    # Translate all components
    translated_message = translate_text(message, language)
    translated_suggestions = translate_text(suggestions, language)
    translated_precautions = translate_text(precautions, language)
    
    return {
        "grade": "A" if wqi >= 80 else "B" if wqi >= 60 else "C",
        "message": translated_message,
        "suggestions": translated_suggestions,
        "precautions": translated_precautions
    }

# Existing routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('water_quality'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        preferred_language = request.form.get('language', 'en')

        # Validate email format
        if not is_valid_email(email):
            flash('Invalid email format. Please enter a valid email address.', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))

        verification_token = generate_verification_token()
        user = User(
            username=username,
            email=email,
            preferred_language=preferred_language,
            verification_token=verification_token
        )
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            send_welcome_email(user)
            flash('Registration successful! Please check your email to verify your account.', 'success')
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'error')
            return redirect(url_for('register'))

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/verify_email/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if user:
        user.email_verified = True
        user.verification_token = None
        db.session.commit()
        flash('Email verified successfully!', 'success')
    else:
        flash('Invalid verification token', 'error')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('water_quality'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password', 'error')
            return render_template('login.html')
        
        try:
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password, password):
                # Check if this is the admin user
                if username == 'admin':
                    user.is_admin = True
                    db.session.commit()
                
                login_user(user)
                
                # Redirect based on user role
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('water_quality'))
            
            flash('Invalid username or password', 'error')
        except Exception as e:
            print(f"Login error: {str(e)}")
            flash('An error occurred during login. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    # Ensure user is admin
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('water_quality'))
    
    try:
        # Get WQI configurations
        configs = WQIConfig.query.all()
        # Get all users except current admin
        users = User.query.filter(User.id != current_user.id).all()
        
        return render_template('admin_dashboard.html', 
                             configs=configs, 
                             users=users,
                             current_user=current_user)
    except Exception as e:
        flash(f'Error loading admin dashboard: {str(e)}', 'error')
        return redirect(url_for('water_quality'))

@app.route('/admin/update_config', methods=['POST'])
@login_required
def update_config():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        config_id = request.form.get('config_id', type=int)
        min_value = request.form.get('min_value', type=float)
        max_value = request.form.get('max_value', type=float)
        weight = request.form.get('weight', type=float)
        
        if None in [config_id, min_value, max_value, weight]:
            return jsonify({'success': False, 'message': 'Invalid parameters'})
        
        config = WQIConfig.query.get(config_id)
        if not config:
            return jsonify({'success': False, 'message': 'Configuration not found'})
        
        config.min_value = min_value
        config.max_value = max_value
        config.weight = weight
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Configuration updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'})
        
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def init_db():
    try:
        with app.app_context():
            # Create database directory if it doesn't exist
            db_dir = os.path.dirname(database_path)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # Create all tables
            db.create_all()
            
            # Check if admin user exists
            admin = User.query.filter_by(username='Vasu').first()
            if not admin:
                # Create default admin user
                admin = User(
                    username='Vasu',
                    email='vasu@example.com',
                    password=generate_password_hash('Vasu@2219'),
                    is_admin=True,
                    thingspeak_channel_id=THINGSPEAK_CHANNEL_ID,
                    thingspeak_read_api_key=THINGSPEAK_READ_API_KEY,
                    password_reset_attempts=0,
                    last_password_reset=None
                )
                db.session.add(admin)
            
            # Initialize WQI configurations
            init_default_config()
            
            db.session.commit()
            print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.session.rollback()
        raise

# Initialize database at startup
with app.app_context():
    init_db()

@app.route('/settings')
@login_required
def settings():
    settings_data = {
        'data_source': current_user.data_source,
        'thingspeak': {
            'channel_id': current_user.thingspeak_channel_id,
            'read_api_key': current_user.thingspeak_read_api_key
        },
        'blink': {
            'auth_token': current_user.blink_auth_token,
            'device_id': current_user.blink_device_id
        }
    }
    return render_template('settings.html', settings=settings_data)

@app.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    try:
        data_source = request.form.get('data_source')
        if data_source not in ['thingspeak', 'blink']:
            flash('Invalid data source selected.', 'error')
            return redirect(url_for('settings'))

        current_user.data_source = data_source

        if data_source == 'thingspeak':
            channel_id = request.form.get('thingspeak_channel_id')
            read_api_key = request.form.get('thingspeak_read_api_key')

            if not channel_id or not read_api_key:
                flash('ThingSpeak Channel ID and Read API Key are required.', 'error')
                return redirect(url_for('settings'))

            current_user.thingspeak_channel_id = channel_id
            current_user.thingspeak_read_api_key = read_api_key

        else:  # Blink
            auth_token = request.form.get('blink_auth_token')
            device_id = request.form.get('blink_device_id')

            if not auth_token or not device_id:
                flash('Blink Authentication Token and Device ID are required.', 'error')
                return redirect(url_for('settings'))

            current_user.blink_auth_token = auth_token
            current_user.blink_device_id = device_id

        db.session.commit()
        flash('Settings updated successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating settings: {str(e)}")
        flash('An error occurred while updating settings.', 'error')

    return redirect(url_for('settings'))

@app.route('/reset_thingspeak_config', methods=['POST'])
@login_required
def reset_thingspeak_config():
    try:
        # Reset to default values from environment variables
        current_user.thingspeak_channel_id = os.getenv('THINGSPEAK_CHANNEL_ID')
        current_user.thingspeak_read_api_key = os.getenv('THINGSPEAK_READ_API_KEY')
        db.session.commit()
        return jsonify({'success': True, 'message': 'ThingSpeak configuration reset to default values'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_thingspeak_config', methods=['POST'])
@login_required
def update_thingspeak_config():
    try:
        channel_id = request.form.get('channel_id')
        read_api_key = request.form.get('read_api_key')
        
        if not channel_id or not read_api_key:
            flash('Please provide both Channel ID and Read API Key', 'error')
            return redirect(url_for('settings'))
        
        # Validate Channel ID format (numbers only)
        if not channel_id.isdigit():
            flash('Invalid Channel ID format. Please enter only numbers.', 'error')
            return redirect(url_for('settings'))
        
        # Validate API Key format (uppercase letters and numbers only)
        if not read_api_key.isalnum() or not all(c.isupper() or c.isdigit() for c in read_api_key):
            flash('Invalid API Key format. Please enter only uppercase letters and numbers.', 'error')
            return redirect(url_for('settings'))
        
        # Test the new configuration
        test_url = f"https://api.thingspeak.com/channels/{channel_id}/feeds/last.json"
        response = requests.get(test_url, params={'api_key': read_api_key}, timeout=10)
        
        if response.status_code != 200:
            flash('Invalid ThingSpeak credentials. Please check your Channel ID and API Key.', 'error')
            return redirect(url_for('settings'))
        
        # Update user's ThingSpeak credentials
        current_user.thingspeak_channel_id = channel_id
        current_user.thingspeak_read_api_key = read_api_key
        db.session.commit()
        
        flash('ThingSpeak configuration updated successfully', 'success')
        return redirect(url_for('settings'))
        
    except requests.Timeout:
        flash('Connection to ThingSpeak timed out. Please try again.', 'error')
    except requests.RequestException as e:
        flash('Failed to connect to ThingSpeak. Please check your internet connection.', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
    
    return redirect(url_for('settings'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    try:
        current_password = request.form.get('currentPassword')
        new_password = request.form.get('newPassword')
        confirm_password = request.form.get('confirmPassword')
        
        if not current_password or not new_password or not confirm_password:
            flash('Please fill in all password fields', 'error')
            return redirect(url_for('settings'))
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('settings'))
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('settings'))
        
        current_user.set_password(new_password)
        db.session.commit()
        flash('Password updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
    
    return redirect(url_for('settings'))

def send_welcome_email(user):
    try:
        print(f"\nPreparing welcome email for user: {user.username}")
        print(f"User email: {user.email}")
        print(f"Verification token: {user.verification_token}")

        msg = Message(
            "Welcome to KARE Water Quality Analysis System",
            recipients=[user.email],
            sender=app.config['MAIL_DEFAULT_SENDER']
        )

        # Create HTML content
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .content {{ margin: 20px 0; }}
                .button {{ 
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #3498db;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{ margin-top: 20px; font-size: 0.9em; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2 class="header">Welcome to KARE Water Quality Analysis System!</h2>
                
                <div class="content">
                    <p>Dear {user.username},</p>
                    
                    <p>Thank you for registering with KARE's Real-Time Water Quality Analysis System!</p>
                    
                    <h3>Our Team:</h3>
                    <ul>
                        <li>G Vasu (Team Lead)</li>
                        <li>Pavan Kumar (Data Analyst)</li>
                        <li>Charan (Backend Developer)</li>
                        <li>Sai Kiran (Frontend Developer)</li>
                        <li>Tharun (IoT Specialist)</li>
                    </ul>
                    
                    <h3>Key Features:</h3>
                    <ol>
                        <li>Real-time Water Quality Monitoring</li>
                        <li>Multi-language Support (English, Telugu, Tamil)</li>
                        <li>Detailed Water Quality Reports</li>
                        <li>Statistical Analysis and Visualizations</li>
                        <li>Customizable Alert System</li>
                        <li>Historical Data Analysis</li>
                        <li>Mobile Responsive Dashboard</li>
                    </ol>
                    
                    <p>To complete your registration, please verify your email by clicking the button below:</p>
                    
                    <a href="{url_for('verify_email', token=user.verification_token, _external=True)}" class="button">
                        Verify Email Address
                    </a>
                    
                    <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                    <p>{url_for('verify_email', token=user.verification_token, _external=True)}</p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message, please do not reply to this email.</p>
                    <p>If you did not register for this service, please ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

        msg.html = html_content
        mail.send(msg)
        print("Welcome email sent successfully!")
        return True

    except Exception as e:
        print(f"Error sending welcome email: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        raise e

def is_valid_email(email):
    """Validate email format."""
    # Regular expression for general email validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def send_water_quality_report(user, data):
    try:
        print("\nPreparing to send water quality report:")
        print(f"User: {user.username}")
        print(f"Email: {user.email}")
        print(f"Language: {user.preferred_language}")

        # Validate email format
        if not is_valid_email(user.email):
            raise ValueError("Invalid email format. Please provide a valid email address.")

        # Generate analysis based on water quality parameters
        analysis = f"""
        Water Quality Analysis Report:
        
        1. Overall Assessment:
        The water quality analysis shows the following parameters:
        - pH Level: {data['ph']} ({get_ph_interpretation(data['ph'], user.preferred_language)['message']})
        - TDS Level: {data['tds']} mg/L ({get_tds_interpretation(data['tds'], user.preferred_language)['message']})
        - Turbidity: {data['turbidity']} NTU ({get_turbidity_interpretation(data['turbidity'], user.preferred_language)['message']})
        - Water Quality Index: {data['wqi']} ({get_overall_interpretation(data['wqi'], user.preferred_language)['message']})
        """
        
        # Get interpretations in user's preferred language
        ph_interpretation = get_ph_interpretation(data['ph'], user.preferred_language)
        tds_interpretation = get_tds_interpretation(data['tds'], user.preferred_language)
        turbidity_interpretation = get_turbidity_interpretation(data['turbidity'], user.preferred_language)
        overall_interpretation = get_overall_interpretation(data['wqi'], user.preferred_language)
        
        # Create visualization
        print("Creating visualization...")
        plt.clf()  # Clear any existing plots
        plot_image_data = create_visualization(data['ph'], data['tds'], data['turbidity'], data['wqi'], data['wqi'])
        
        print("Preparing email message...")
        msg = Message(
            subject='Water Quality Analysis Report',
            recipients=[user.email],
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        
        # Create HTML content
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
                    Water Quality Analysis Report
                </h2>
                
                <p>Dear {user.username},</p>
                
                <h3 style="color: #2c3e50;">Current Parameters:</h3>
                <ul>
                    <li>pH: {data['ph']}</li>
                    <li>TDS: {data['tds']} mg/L</li>
                    <li>Turbidity: {data['turbidity']} NTU</li>
                    <li>Water Quality Index (WQI): {data['wqi']}</li>
                </ul>
                
                <div style="margin: 20px 0;">
                    <h4 style="color: #3498db;">Analysis Results</h4>
                    <p>{analysis}</p>
                </div>
                
                <div style="margin: 20px 0;">
                    <h4 style="color: #3498db;">Recommendations</h4>
                    <p>{overall_interpretation['suggestions']}</p>
                </div>
                
                <div style="margin: 20px 0;">
                    <h4 style="color: #3498db;">Precautions</h4>
                    <p>{overall_interpretation['precautions']}</p>
                </div>
                
                <h3 style="color: #2c3e50;">Visualization:</h3>
                <img src="cid:plot" alt="Water Quality Visualization" style="max-width: 100%;">
                
                <p style="margin-top: 20px; font-size: 0.9em; color: #666;">
                    Report Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
                
                <p style="margin-top: 20px;">
                    Best regards,<br>
                    KARE Water Quality Analysis Team
                </p>
            </body>
        </html>
        """
        
        msg.html = html_content
        
        # Attach the plot image
        if plot_image_data:
            print("Attaching visualization to email...")
            plot_image_bytes = base64.b64decode(plot_image_data)
            msg.attach("plot.png", "image/png", plot_image_bytes, 'inline', headers=[['Content-ID', '<plot>']])
        
        print("Sending email...")
        mail.send(msg)
        print("Email sent successfully!")
        
        return True
        
    except Exception as e:
        print(f"Error sending report: {str(e)}")
        print(f"Error details: {type(e).__name__}")
        raise e

@app.route('/send_report', methods=['POST'])
@login_required
def send_report():
    try:
        data = request.get_json()
        print(f"Received report data: {data}")  # Debug log
        
        # Get user's email from the current user
        user_email = current_user.email
        if not user_email:
            return jsonify({'status': 'error', 'message': 'User email not found'}), 400
        
        # Create email message
        msg = Message(
            f"Water Quality Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            recipients=[user_email],
            sender=app.config['MAIL_DEFAULT_SENDER']
        )

        # Generate treatment recommendations based on sensor data
        treatment_recommendations = generate_treatment_recommendations(data)
        conservation_tips = generate_conservation_tips(data)
        utilization_guidelines = generate_utilization_guidelines(data)
        emergency_measures = generate_emergency_measures(data)
        maintenance_guidelines = generate_maintenance_guidelines(data)

        # Create HTML content
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .parameter {{ margin-bottom: 20px; }}
                .parameter h3 {{ color: #2c3e50; margin-bottom: 10px; }}
                .value {{ font-size: 18px; font-weight: bold; color: #3498db; }}
                .interpretation {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 10px; }}
                .suggestions {{ color: #27ae60; }}
                .precautions {{ color: #e74c3c; }}
                .section {{ margin: 30px 0; }}
                .section h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .treatment-method {{ background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .conservation-tip {{ background-color: #e8f8f0; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .utilization-guideline {{ background-color: #f8f8e8; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .emergency-measure {{ background-color: #f8e8e8; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .maintenance-guideline {{ background-color: #e8e8f8; padding: 15px; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Water Quality Analysis Report</h2>
                <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                
                <div class="parameter">
                    <h3>pH Level</h3>
                    <div class="value">{data['ph']:.2f}</div>
                    <div class="interpretation">
                        <p><strong>Analysis:</strong> {data['interpretation']['ph']['message']}</p>
                        <p class="suggestions"><strong>Suggestions:</strong> {data['interpretation']['ph']['suggestions']}</p>
                        <p class="precautions"><strong>Precautions:</strong> {data['interpretation']['ph']['precautions']}</p>
                    </div>
                </div>
                
                <div class="parameter">
                    <h3>TDS (Total Dissolved Solids)</h3>
                    <div class="value">{data['tds']:.2f} mg/L</div>
                    <div class="interpretation">
                        <p><strong>Analysis:</strong> {data['interpretation']['tds']['message']}</p>
                        <p class="suggestions"><strong>Suggestions:</strong> {data['interpretation']['tds']['suggestions']}</p>
                        <p class="precautions"><strong>Precautions:</strong> {data['interpretation']['tds']['precautions']}</p>
                    </div>
                </div>
                
                <div class="parameter">
                    <h3>Turbidity</h3>
                    <div class="value">{data['turbidity']:.2f} NTU</div>
                    <div class="interpretation">
                        <p><strong>Analysis:</strong> {data['interpretation']['turbidity']['message']}</p>
                        <p class="suggestions"><strong>Suggestions:</strong> {data['interpretation']['turbidity']['suggestions']}</p>
                        <p class="precautions"><strong>Precautions:</strong> {data['interpretation']['turbidity']['precautions']}</p>
                    </div>
                </div>
                
                <div class="parameter">
                    <h3>Water Quality Index (WQI)</h3>
                    <div class="value">{data['wqi']:.2f}</div>
                    <div class="interpretation">
                        <p><strong>Overall Analysis:</strong> {data['interpretation']['overall']['message']}</p>
                        <p class="suggestions"><strong>Suggestions:</strong> {data['interpretation']['overall']['suggestions']}</p>
                        <p class="precautions"><strong>Precautions:</strong> {data['interpretation']['overall']['precautions']}</p>
                    </div>
                </div>

                <div class="section">
                    <h2>Recommended Water Treatment Methods</h2>
                    {treatment_recommendations}
                </div>

                <div class="section">
                    <h2>Water Conservation Tips</h2>
                    {conservation_tips}
                </div>

                <div class="section">
                    <h2>Water Utilization Guidelines</h2>
                    {utilization_guidelines}
                </div>

                <div class="section">
                    <h2>Emergency Measures</h2>
                    {emergency_measures}
                </div>

                <div class="section">
                    <h2>System Maintenance Guidelines</h2>
                    {maintenance_guidelines}
                </div>
            </div>
        </body>
        </html>
        """

        msg.html = html_content
        mail.send(msg)
        print(f"Report sent successfully to {user_email}")  # Debug log
        return jsonify({'status': 'success', 'message': 'Report sent successfully'})
        
    except Exception as e:
        print(f"Error sending report: {str(e)}")  # Debug log
        return jsonify({'status': 'error', 'message': str(e)}), 500

def generate_treatment_recommendations(data):
    recommendations = []
    
    # pH-based treatments
    if data['ph'] < 6.5:
        recommendations.append("""
        <div class="treatment-method">
            <h4>Acidic Water Treatment</h4>
            <ul>
                <li>Install a pH neutralization system using calcium carbonate or soda ash</li>
                <li>Consider using a calcite filter for mild acidity</li>
                <li>Regular monitoring of pH levels after treatment</li>
                <li>Use of food-grade citric acid for precise pH adjustment</li>
                <li>Implement aeration systems to naturally increase pH</li>
                <li>Consider using limestone contactors for continuous pH adjustment</li>
                <li>Use of magnesium oxide for pH correction</li>
                <li>Implement chemical feed systems for large-scale treatment</li>
                <li>Consider using pH balancing filters</li>
                <li>Use of sodium hydroxide for rapid pH adjustment</li>
            </ul>
        </div>
        """)
    elif data['ph'] > 8.5:
        recommendations.append("""
        <div class="treatment-method">
            <h4>Alkaline Water Treatment</h4>
            <ul>
                <li>Install an acid injection system using food-grade phosphoric acid</li>
                <li>Consider using a reverse osmosis system for comprehensive treatment</li>
                <li>Regular monitoring of pH levels after treatment</li>
                <li>Use of carbon dioxide injection for precise pH adjustment</li>
                <li>Implement acid dosing systems for large-scale treatment</li>
                <li>Consider using ion exchange systems for pH reduction</li>
                <li>Use of sulfuric acid for rapid pH reduction</li>
                <li>Implement pH balancing filters</li>
                <li>Consider using acid neutralization tanks</li>
                <li>Use of hydrochloric acid for industrial applications</li>
            </ul>
        </div>
        """)
    
    # TDS-based treatments
    if data['tds'] > 500:
        recommendations.append("""
        <div class="treatment-method">
            <h4>High TDS Treatment</h4>
            <ul>
                <li>Install a reverse osmosis (RO) system for comprehensive treatment</li>
                <li>Consider using a water softener for hardness reduction</li>
                <li>Regular maintenance of treatment systems</li>
                <li>Use of activated carbon filters for organic matter removal</li>
                <li>Consider distillation for critical applications</li>
                <li>Implement electrodialysis for selective ion removal</li>
                <li>Use of nanofiltration for partial desalination</li>
                <li>Consider using deionization systems for ultra-pure water</li>
                <li>Implement multi-stage filtration systems</li>
                <li>Use of ion exchange resins for specific ion removal</li>
                <li>Consider using membrane distillation</li>
                <li>Implement capacitive deionization for energy-efficient treatment</li>
            </ul>
        </div>
        """)
    
    # Turbidity-based treatments
    if data['turbidity'] > 1:
        recommendations.append("""
        <div class="treatment-method">
            <h4>Turbidity Treatment</h4>
            <ul>
                <li>Install a multi-stage filtration system</li>
                <li>Use of coagulants and flocculants for particle removal</li>
                <li>Consider using a sand filter or multimedia filter</li>
                <li>Regular backwashing of filters</li>
                <li>Use of ultrafiltration for fine particle removal</li>
                <li>Implement sedimentation tanks for large particles</li>
                <li>Consider using membrane filtration for high-quality water</li>
                <li>Use of dissolved air flotation for efficient particle removal</li>
                <li>Implement cartridge filters for fine particle removal</li>
                <li>Use of diatomaceous earth filters for high turbidity</li>
                <li>Consider using bag filters for large-scale treatment</li>
                <li>Implement pre-filtration systems for better efficiency</li>
            </ul>
        </div>
        """)
    
    return "\n".join(recommendations)

def generate_conservation_tips(data):
    tips = []
    
    # General conservation tips
    tips.append("""
    <div class="conservation-tip">
        <h4>General Water Conservation</h4>
        <ul>
            <li>Fix leaks promptly to prevent water wastage</li>
            <li>Install water-efficient fixtures and appliances</li>
            <li>Collect rainwater for non-potable uses</li>
            <li>Use drip irrigation for gardens and landscapes</li>
            <li>Implement water recycling systems where possible</li>
            <li>Use water-efficient appliances (WELS rated)</li>
            <li>Install water-saving showerheads and faucets</li>
            <li>Implement greywater systems for garden irrigation</li>
            <li>Use mulch in gardens to reduce evaporation</li>
            <li>Consider xeriscaping for water-efficient landscaping</li>
            <li>Install smart irrigation controllers</li>
            <li>Use rain sensors for automatic irrigation control</li>
            <li>Implement water-efficient cooling systems</li>
            <li>Use water-efficient industrial processes</li>
            <li>Consider using waterless urinals and low-flow toilets</li>
        </ul>
    </div>
    """)
    
    # Quality-specific conservation tips
    if data['wqi'] < 60:
        tips.append("""
        <div class="conservation-tip">
            <h4>Poor Quality Water Conservation</h4>
            <ul>
                <li>Implement greywater systems for non-potable uses</li>
                <li>Use treated water only for essential purposes</li>
                <li>Consider alternative water sources for critical needs</li>
                <li>Regular maintenance of treatment systems</li>
                <li>Monitor water quality frequently</li>
                <li>Implement dual plumbing systems for different water qualities</li>
                <li>Use water-efficient appliances to reduce treatment needs</li>
                <li>Consider rainwater harvesting for non-potable uses</li>
                <li>Implement water reuse systems for industrial processes</li>
                <li>Use water-efficient cooling systems</li>
                <li>Implement water quality monitoring systems</li>
                <li>Use automated treatment systems for consistent quality</li>
                <li>Consider using alternative water sources</li>
                <li>Implement water quality alerts and notifications</li>
                <li>Use water-efficient treatment processes</li>
            </ul>
        </div>
        """)
    
    return "\n".join(tips)

def generate_utilization_guidelines(data):
    guidelines = []
    
    # pH-based guidelines
    if 6.5 <= data['ph'] <= 8.5:
        guidelines.append("""
        <div class="utilization-guideline">
            <h4>Safe Water Usage</h4>
            <ul>
                <li>Safe for drinking and cooking</li>
                <li>Ideal for bathing and personal hygiene</li>
                <li>Suitable for laundry and dishwashing</li>
                <li>Safe for pets and plants</li>
                <li>Good for food preparation and cooking</li>
                <li>Suitable for aquariums and hydroponics</li>
                <li>Ideal for brewing and beverage production</li>
                <li>Safe for medical and laboratory use</li>
                <li>Good for industrial processes</li>
                <li>Suitable for agricultural irrigation</li>
            </ul>
        </div>
        """)
    else:
        guidelines.append("""
        <div class="utilization-guideline">
            <h4>Restricted Water Usage</h4>
            <ul>
                <li>Use only after proper treatment</li>
                <li>Avoid direct consumption</li>
                <li>Not recommended for sensitive applications</li>
                <li>Consider alternative water sources for critical needs</li>
                <li>Not suitable for food preparation</li>
                <li>Avoid use in medical applications</li>
                <li>Not recommended for aquariums</li>
                <li>Use with caution for irrigation</li>
                <li>Not suitable for industrial processes</li>
                <li>Consider treatment before any use</li>
            </ul>
        </div>
        """)
    
    # TDS-based guidelines
    if data['tds'] <= 500:
        guidelines.append("""
        <div class="utilization-guideline">
            <h4>Low TDS Water Usage</h4>
            <ul>
                <li>Ideal for drinking and cooking</li>
                <li>Good for sensitive applications</li>
                <li>Suitable for all household uses</li>
                <li>Safe for aquariums and hydroponics</li>
                <li>Excellent for beverage production</li>
                <li>Ideal for medical applications</li>
                <li>Good for laboratory use</li>
                <li>Suitable for industrial processes</li>
                <li>Excellent for food preparation</li>
                <li>Ideal for sensitive equipment</li>
            </ul>
        </div>
        """)
    
    # Turbidity-based guidelines
    if data['turbidity'] <= 1:
        guidelines.append("""
        <div class="utilization-guideline">
            <h4>Clear Water Usage</h4>
            <ul>
                <li>Ideal for all household applications</li>
                <li>Perfect for aesthetic uses</li>
                <li>Suitable for sensitive equipment</li>
                <li>Good for food preparation</li>
                <li>Excellent for beverage production</li>
                <li>Ideal for medical applications</li>
                <li>Good for laboratory use</li>
                <li>Suitable for industrial processes</li>
                <li>Excellent for aquariums</li>
                <li>Ideal for hydroponics</li>
            </ul>
        </div>
        """)
    
    return "\n".join(guidelines)

def generate_emergency_measures(data):
    measures = []
    
    # Emergency measures based on water quality
    if data['wqi'] < 60:
        measures.append("""
        <div class="emergency-measure">
            <h4>Emergency Water Treatment Measures</h4>
            <ul>
                <li>Boil water for at least 1 minute before consumption</li>
                <li>Use water purification tablets or drops</li>
                <li>Implement emergency filtration systems</li>
                <li>Consider using portable RO systems</li>
                <li>Use UV sterilization for emergency treatment</li>
                <li>Implement emergency chlorination if needed</li>
                <li>Consider using emergency water storage</li>
                <li>Use bottled water for drinking and cooking</li>
                <li>Implement emergency water distribution systems</li>
                <li>Consider using emergency water treatment plants</li>
                <li>Use emergency water quality testing kits</li>
                <li>Implement emergency water rationing systems</li>
                <li>Consider using emergency water purification systems</li>
                <li>Use emergency water storage tanks</li>
                <li>Implement emergency water quality monitoring</li>
            </ul>
        </div>
        """)
    
    return "\n".join(measures)

def generate_maintenance_guidelines(data):
    guidelines = []
    
    # General maintenance guidelines
    guidelines.append("""
    <div class="maintenance-guideline">
        <h4>System Maintenance Guidelines</h4>
        <ul>
            <li>Regular cleaning and replacement of filters</li>
            <li>Monthly inspection of treatment systems</li>
            <li>Quarterly calibration of sensors and equipment</li>
            <li>Annual comprehensive system check</li>
            <li>Regular monitoring of water quality parameters</li>
            <li>Maintenance of backup power systems</li>
            <li>Regular cleaning of storage tanks</li>
            <li>Inspection of distribution systems</li>
            <li>Maintenance of control systems</li>
            <li>Regular training of maintenance personnel</li>
            <li>Implementation of preventive maintenance schedules</li>
            <li>Regular testing of water quality parameters</li>
            <li>Maintenance of treatment system components</li>
            <li>Regular inspection of pipes and valves</li>
            <li>Implementation of maintenance tracking systems</li>
        </ul>
    </div>
    """)
    
    return "\n".join(guidelines)

def generate_verification_token():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

def translate_text(text, target_lang):
    try:
        translation = translator.translate(text, dest=target_lang)
        return translation.text
    except:
        return text

@app.route('/generate_report', methods=['POST'])
@login_required
def generate_report():
    data = request.json
    user_lang = current_user.preferred_language
    
    # Use Gemini API for analysis
    model = genai.GenerativeModel('gemini-1.0-pro')
    analysis = model.generate_content(f"""
    Analyze this water quality data and provide a detailed report:
    pH: {data['ph']}
    TDS: {data['tds']}
    Turbidity: {data['turbidity']}
    WQI: {data['wqi']}
    
    Please provide:
    1. Overall water quality assessment
    2. Health implications
    3. Recommendations
    4. Statistical insights
    """)
    
    # Translate the report to user's preferred language
    translated_report = translate_text(analysis.text, user_lang)
    
    return jsonify({
        'report': translated_report,
        'language': user_lang
    })

@app.route('/change_language', methods=['POST'])
@login_required
def change_language():
    if request.method == 'POST':
        language = request.form.get('language')
        if language in ['en', 'te', 'ta']:
            current_user.preferred_language = language
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'})

@app.route('/test_email')
def test_email():
    try:
        if not app.config['MAIL_USERNAME']:
            return 'Email configuration is missing. Please check your .env file.'

        # Validate email format
        if not is_valid_email(app.config['MAIL_USERNAME']):
            return 'Invalid email format. Please provide a valid email address.'

        print(f"Sending test email to: {app.config['MAIL_USERNAME']}")
        print(f"Using SMTP server: {app.config['MAIL_SERVER']}")
        print(f"Using port: {app.config['MAIL_PORT']}")
        print(f"TLS enabled: {app.config['MAIL_USE_TLS']}")
        print(f"SSL enabled: {app.config['MAIL_USE_SSL']}")

        msg = Message(
            'Test Email from KARE Water Quality Analysis',
            sender=app.config['MAIL_DEFAULT_SENDER'],
            recipients=[app.config['MAIL_USERNAME']]
        )
        msg.body = 'This is a test email to verify the email configuration.'
        msg.html = '''
        <h3>Email Configuration Test</h3>
        <p>This is a test email to verify that the email configuration is working correctly.</p>
        <p>If you received this email, it means your email settings are configured properly.</p>
        '''
        
        mail.send(msg)
        return 'Test email sent successfully! Please check your inbox.'
    except Exception as e:
        error_msg = f'Error sending test email: {str(e)}'
        print(error_msg)
        return error_msg

@app.route('/update_thingspeak_settings', methods=['POST'])
@login_required
def update_thingspeak_settings():
    if not current_user.is_admin:
        flash('Only administrators can update ThingSpeak settings', 'error')
        return redirect(url_for('settings'))
    
    channel_id = request.form.get('channelId')
    read_api_key = request.form.get('readApiKey')
    
    if not all([channel_id, read_api_key]):
        flash('Please provide both Channel ID and Read API Key', 'error')
        return redirect(url_for('settings'))
    
    try:
        # Update environment variables
        os.environ['THINGSPEAK_CHANNEL_ID'] = channel_id
        os.environ['THINGSPEAK_READ_API_KEY'] = read_api_key
        
        # Update app config
        app.config['THINGSPEAK_CHANNEL_ID'] = channel_id
        app.config['THINGSPEAK_READ_API_KEY'] = read_api_key
        
        # Update .env file
        dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
        set_key(dotenv_path, 'THINGSPEAK_CHANNEL_ID', channel_id)
        set_key(dotenv_path, 'THINGSPEAK_READ_API_KEY', read_api_key)
        
        flash('ThingSpeak settings updated successfully', 'success')
    except Exception as e:
        print(f"Error updating ThingSpeak settings: {str(e)}")
        flash('Error updating ThingSpeak settings', 'error')
    
    return redirect(url_for('settings'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
