# database/broker_credentials_db.py

import os
import json
import base64
import pyotp
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from cachetools import TTLCache
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')
PEPPER = os.getenv('API_KEY_PEPPER', 'default-pepper-change-in-production')

# Setup Fernet encryption for credentials
def get_encryption_key():
    """Generate a Fernet key from the pepper"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'openalgo_credentials_salt',
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(PEPPER.encode()))
    return Fernet(key)

# Initialize Fernet cipher
fernet = get_encryption_key()

# Define caches for credentials with TTL
broker_api_cache = TTLCache(maxsize=256, ttl=1800)  # 30 minutes
user_credentials_cache = TTLCache(maxsize=1024, ttl=300)  # 5 minutes

engine = create_engine(
    DATABASE_URL,
    pool_size=50,
    max_overflow=100,
    pool_timeout=10
)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

class BrokerApiCredentials(Base):
    """System-wide broker API credentials (admin configured)"""
    __tablename__ = 'broker_api_credentials'
    
    id = Column(Integer, primary_key=True)
    broker_name = Column(String(50), unique=True, nullable=False)
    api_key = Column(Text, nullable=False)  # Encrypted
    api_secret = Column(Text, nullable=True)  # Encrypted
    additional_config = Column(Text, nullable=True)  # JSON for broker-specific config
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class UserTradingCredentials(Base):
    """User-specific trading credentials (per user, per broker)"""
    __tablename__ = 'user_trading_credentials'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False)
    broker_name = Column(String(50), nullable=False)
    
    # User's trading account details (broker-specific, encrypted)
    client_id = Column(Text, nullable=True)  # Angel One, etc.
    user_id_broker = Column(Text, nullable=True)  # Zebu, AliceBlue, etc.
    mobile_number = Column(Text, nullable=True)  # Kotak
    password = Column(Text, nullable=True)  # Zebu, Kotak, etc.
    pin = Column(Text, nullable=True)  # Angel One
    
    # TOTP Configuration
    totp_option = Column(String(20), nullable=False, default='manual')  # 'stored' or 'manual'
    totp_secret = Column(Text, nullable=True)  # Encrypted TOTP secret (only if totp_option = 'stored')
    
    # Additional broker-specific fields
    additional_fields = Column(Text, nullable=True)  # JSON for broker-specific data
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    # Unique constraint: one credential set per user per broker
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

def init_db():
    """Initialize broker credentials database"""
    logger.info("Initializing Broker Credentials DB")
    Base.metadata.create_all(bind=engine)

# Encryption/Decryption utilities
def encrypt_data(data):
    """Encrypt sensitive data"""
    if not data:
        return ''
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    """Decrypt sensitive data"""
    if not encrypted_data:
        return ''
    try:
        return fernet.decrypt(encrypted_data.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting data: {e}")
        return None

# Broker API Credentials Management
def upsert_broker_api_credentials(broker_name, api_key, api_secret=None, additional_config=None):
    """Store or update broker API credentials"""
    try:
        encrypted_api_key = encrypt_data(api_key)
        encrypted_api_secret = encrypt_data(api_secret) if api_secret else None
        encrypted_config = encrypt_data(json.dumps(additional_config)) if additional_config else None
        
        broker_creds = BrokerApiCredentials.query.filter_by(broker_name=broker_name).first()
        if broker_creds:
            broker_creds.api_key = encrypted_api_key
            broker_creds.api_secret = encrypted_api_secret
            broker_creds.additional_config = encrypted_config
            broker_creds.updated_at = func.now()
        else:
            broker_creds = BrokerApiCredentials(
                broker_name=broker_name,
                api_key=encrypted_api_key,
                api_secret=encrypted_api_secret,
                additional_config=encrypted_config
            )
            db_session.add(broker_creds)
        
        db_session.commit()
        
        # Clear cache
        cache_key = f"broker_api_{broker_name}"
        if cache_key in broker_api_cache:
            del broker_api_cache[cache_key]
            
        logger.info(f"Successfully stored API credentials for broker: {broker_name}")
        return broker_creds.id
        
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error storing broker API credentials: {e}")
        return None

def get_broker_api_credentials(broker_name):
    """Get decrypted broker API credentials"""
    cache_key = f"broker_api_{broker_name}"
    
    if cache_key in broker_api_cache:
        return broker_api_cache[cache_key]
    
    try:
        broker_creds = BrokerApiCredentials.query.filter_by(
            broker_name=broker_name, 
            is_active=True
        ).first()
        
        if not broker_creds:
            logger.warning(f"No API credentials found for broker: {broker_name}")
            return None
        
        decrypted_creds = {
            'broker_name': broker_name,
            'api_key': decrypt_data(broker_creds.api_key),
            'api_secret': decrypt_data(broker_creds.api_secret) if broker_creds.api_secret else None,
            'additional_config': json.loads(decrypt_data(broker_creds.additional_config)) if broker_creds.additional_config else None
        }
        
        # Cache the result
        broker_api_cache[cache_key] = decrypted_creds
        return decrypted_creds
        
    except Exception as e:
        logger.error(f"Error retrieving broker API credentials: {e}")
        return None

def list_active_brokers():
    """List all active brokers with API credentials"""
    try:
        brokers = BrokerApiCredentials.query.filter_by(is_active=True).all()
        return [{'broker_name': broker.broker_name, 'id': broker.id} for broker in brokers]
    except Exception as e:
        logger.error(f"Error listing active brokers: {e}")
        return []

# User Trading Credentials Management
def upsert_user_trading_credentials(user_id, broker_name, credentials, totp_option='manual', totp_secret=None):
    """Store or update user trading credentials"""
    try:
        # Encrypt all credential fields
        encrypted_creds = {}
        for field, value in credentials.items():
            if value:
                encrypted_creds[field] = encrypt_data(str(value))
        
        encrypted_totp_secret = encrypt_data(totp_secret) if totp_secret else None
        
        user_creds = UserTradingCredentials.query.filter_by(
            user_id=user_id, 
            broker_name=broker_name
        ).first()
        
        if user_creds:
            # Update existing credentials
            for field in ['client_id', 'user_id_broker', 'mobile_number', 'password', 'pin']:
                if field in encrypted_creds:
                    setattr(user_creds, field, encrypted_creds[field])
            
            user_creds.totp_option = totp_option
            user_creds.totp_secret = encrypted_totp_secret
            user_creds.updated_at = func.now()
        else:
            # Create new credentials
            user_creds = UserTradingCredentials(
                user_id=user_id,
                broker_name=broker_name,
                client_id=encrypted_creds.get('client_id'),
                user_id_broker=encrypted_creds.get('user_id_broker'),
                mobile_number=encrypted_creds.get('mobile_number'),
                password=encrypted_creds.get('password'),
                pin=encrypted_creds.get('pin'),
                totp_option=totp_option,
                totp_secret=encrypted_totp_secret
            )
            db_session.add(user_creds)
        
        db_session.commit()
        
        # Clear cache
        cache_key = f"user_creds_{user_id}_{broker_name}"
        if cache_key in user_credentials_cache:
            del user_credentials_cache[cache_key]
        
        logger.info(f"Successfully stored trading credentials for user {user_id}, broker {broker_name}")
        return user_creds.id
        
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error storing user trading credentials: {e}")
        return None

def get_user_trading_credentials(user_id, broker_name):
    """Get decrypted user trading credentials"""
    cache_key = f"user_creds_{user_id}_{broker_name}"
    
    if cache_key in user_credentials_cache:
        return user_credentials_cache[cache_key]
    
    try:
        user_creds = UserTradingCredentials.query.filter_by(
            user_id=user_id,
            broker_name=broker_name,
            is_active=True
        ).first()
        
        if not user_creds:
            logger.warning(f"No trading credentials found for user {user_id}, broker {broker_name}")
            return None
        
        decrypted_creds = {
            'user_id': user_id,
            'broker_name': broker_name,
            'client_id': decrypt_data(user_creds.client_id) if user_creds.client_id else None,
            'user_id_broker': decrypt_data(user_creds.user_id_broker) if user_creds.user_id_broker else None,
            'mobile_number': decrypt_data(user_creds.mobile_number) if user_creds.mobile_number else None,
            'password': decrypt_data(user_creds.password) if user_creds.password else None,
            'pin': decrypt_data(user_creds.pin) if user_creds.pin else None,
            'totp_option': user_creds.totp_option,
            'totp_secret': decrypt_data(user_creds.totp_secret) if user_creds.totp_secret else None
        }
        
        # Cache the result
        user_credentials_cache[cache_key] = decrypted_creds
        return decrypted_creds
        
    except Exception as e:
        logger.error(f"Error retrieving user trading credentials: {e}")
        return None

def get_user_brokers(user_id):
    """Get list of brokers configured for a user"""
    try:
        user_brokers = UserTradingCredentials.query.filter_by(
            user_id=user_id,
            is_active=True
        ).all()
        
        return [
            {
                'broker_name': ub.broker_name,
                'totp_option': ub.totp_option,
                'created_at': ub.created_at
            } 
            for ub in user_brokers
        ]
        
    except Exception as e:
        logger.error(f"Error getting user brokers: {e}")
        return []

# TOTP Management
class TOTPManager:
    """TOTP management utilities"""
    
    @staticmethod
    def generate_totp_from_secret(secret_key):
        """Generate current TOTP from secret"""
        try:
            totp = pyotp.TOTP(secret_key)
            return totp.now()
        except Exception as e:
            logger.error(f"Error generating TOTP: {e}")
            return None
    
    @staticmethod
    def validate_totp_secret(secret_key, expected_totp):
        """Validate TOTP secret by checking generated code"""
        try:
            totp = pyotp.TOTP(secret_key)
            return totp.verify(expected_totp)  # pyotp handles the time window automatically
        except Exception as e:
            logger.error(f"Error validating TOTP secret: {e}")
            return False
    
    @staticmethod
    def get_user_totp(user_id, broker_name):
        """Generate TOTP for user if they have stored secret"""
        try:
            user_creds = get_user_trading_credentials(user_id, broker_name)
            if not user_creds:
                return None
                
            if user_creds['totp_option'] == 'stored' and user_creds['totp_secret']:
                return TOTPManager.generate_totp_from_secret(user_creds['totp_secret'])
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user TOTP: {e}")
            return None

# Combined credentials retrieval
def get_combined_credentials(user_id, broker_name):
    """Get both broker API credentials and user trading credentials"""
    try:
        broker_api_creds = get_broker_api_credentials(broker_name)
        user_trading_creds = get_user_trading_credentials(user_id, broker_name)
        
        if not broker_api_creds:
            logger.error(f"No API credentials configured for broker: {broker_name}")
            return None
            
        if not user_trading_creds:
            logger.error(f"No trading credentials configured for user {user_id}, broker {broker_name}")
            return None
        
        return {
            'broker_api': broker_api_creds,
            'user_trading': user_trading_creds
        }
        
    except Exception as e:
        logger.error(f"Error getting combined credentials: {e}")
        return None

# Cleanup and maintenance functions
def deactivate_user_credentials(user_id, broker_name):
    """Deactivate user credentials for a broker"""
    try:
        user_creds = UserTradingCredentials.query.filter_by(
            user_id=user_id,
            broker_name=broker_name
        ).first()
        
        if user_creds:
            user_creds.is_active = False
            db_session.commit()
            
            # Clear cache
            cache_key = f"user_creds_{user_id}_{broker_name}"
            if cache_key in user_credentials_cache:
                del user_credentials_cache[cache_key]
                
            return True
        return False
        
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error deactivating user credentials: {e}")
        return False

def clear_credentials_cache():
    """Clear all credentials caches"""
    broker_api_cache.clear()
    user_credentials_cache.clear()
    logger.info("Cleared all credentials caches")
