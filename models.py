"""Global Ai buildathon"""
# Updated for hackathon submission: 2025-08-23
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    thingspeak_channel_id = db.Column(db.String(50))
    thingspeak_read_api_key = db.Column(db.String(50))
    password_reset_attempts = db.Column(db.Integer, default=0, nullable=True)
    last_password_reset = db.Column(db.DateTime, nullable=True)
    preferred_language = db.Column(db.String(10), default='en')  # en, te, ta
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class WQIConfig(db.Model):
    __tablename__ = 'wqi_config'
    id = db.Column(db.Integer, primary_key=True)
    parameter = db.Column(db.String(50), nullable=False)
    min_value = db.Column(db.Float, nullable=False)
    max_value = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<WQIConfig {self.parameter}>' 