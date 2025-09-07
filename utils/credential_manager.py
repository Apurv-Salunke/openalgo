# utils/credential_manager.py

"""
Credential management utilities for OpenAlgo multi-broker system.

This module provides high-level functions for managing broker API credentials
and user trading credentials, abstracting away the database operations.
"""

import json
from typing import Dict, List, Optional, Any
from database.broker_credentials_db import (
    upsert_broker_api_credentials,
    get_broker_api_credentials,
    list_active_brokers,
    upsert_user_trading_credentials,
    get_user_trading_credentials,
    get_user_brokers,
    get_combined_credentials,
    deactivate_user_credentials,
    TOTPManager
)
from utils.logging import get_logger

logger = get_logger(__name__)

class CredentialManager:
    """High-level credential management interface"""
    
    @staticmethod
    def setup_broker_api(broker_name: str, api_key: str, api_secret: str = None, 
                        additional_config: Dict = None) -> bool:
        """
        Set up broker API credentials (admin function)
        
        Args:
            broker_name: Name of the broker (e.g., 'angel', 'zebu')
            api_key: Broker API key
            api_secret: Broker API secret (optional)
            additional_config: Additional broker-specific configuration
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = upsert_broker_api_credentials(
                broker_name=broker_name,
                api_key=api_key,
                api_secret=api_secret,
                additional_config=additional_config
            )
            
            if result:
                logger.info(f"Successfully set up API credentials for broker: {broker_name}")
                return True
            else:
                logger.error(f"Failed to set up API credentials for broker: {broker_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting up broker API credentials: {e}")
            return False
    
    @staticmethod
    def get_broker_api(broker_name: str) -> Optional[Dict]:
        """
        Get broker API credentials
        
        Args:
            broker_name: Name of the broker
            
        Returns:
            Dict with broker API credentials or None if not found
        """
        try:
            return get_broker_api_credentials(broker_name)
        except Exception as e:
            logger.error(f"Error getting broker API credentials: {e}")
            return None
    
    @staticmethod
    def list_configured_brokers() -> List[Dict]:
        """
        List all brokers with configured API credentials
        
        Returns:
            List of broker information dictionaries
        """
        try:
            return list_active_brokers()
        except Exception as e:
            logger.error(f"Error listing configured brokers: {e}")
            return []
    
    @staticmethod
    def setup_user_credentials(user_id: str, broker_name: str, credentials: Dict,
                             totp_option: str = 'manual', totp_secret: str = None) -> bool:
        """
        Set up user trading credentials
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            credentials: Dictionary of user credentials (client_id, pin, etc.)
            totp_option: 'manual' or 'stored'
            totp_secret: TOTP secret key (required if totp_option='stored')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate TOTP setup if storing secret
            if totp_option == 'stored':
                if not totp_secret:
                    logger.error("TOTP secret required when totp_option='stored'")
                    return False
                
                # Validate TOTP secret by generating a code
                test_totp = TOTPManager.generate_totp_from_secret(totp_secret)
                if not test_totp:
                    logger.error("Invalid TOTP secret provided")
                    return False
            
            result = upsert_user_trading_credentials(
                user_id=user_id,
                broker_name=broker_name,
                credentials=credentials,
                totp_option=totp_option,
                totp_secret=totp_secret
            )
            
            if result:
                logger.info(f"Successfully set up trading credentials for user {user_id}, broker {broker_name}")
                return True
            else:
                logger.error(f"Failed to set up trading credentials for user {user_id}, broker {broker_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting up user trading credentials: {e}")
            return False
    
    @staticmethod
    def get_user_credentials(user_id: str, broker_name: str) -> Optional[Dict]:
        """
        Get user trading credentials
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            
        Returns:
            Dict with user trading credentials or None if not found
        """
        try:
            return get_user_trading_credentials(user_id, broker_name)
        except Exception as e:
            logger.error(f"Error getting user trading credentials: {e}")
            return None
    
    @staticmethod
    def get_user_broker_list(user_id: str) -> List[Dict]:
        """
        Get list of brokers configured for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            List of broker configurations for the user
        """
        try:
            return get_user_brokers(user_id)
        except Exception as e:
            logger.error(f"Error getting user broker list: {e}")
            return []
    
    @staticmethod
    def get_authentication_credentials(user_id: str, broker_name: str) -> Optional[Dict]:
        """
        Get combined credentials for broker authentication
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            
        Returns:
            Dict with both broker API and user trading credentials
        """
        try:
            return get_combined_credentials(user_id, broker_name)
        except Exception as e:
            logger.error(f"Error getting authentication credentials: {e}")
            return None
    
    @staticmethod
    def generate_user_totp(user_id: str, broker_name: str) -> Optional[str]:
        """
        Generate TOTP code for user (if they have stored secret)
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            
        Returns:
            6-digit TOTP code or None if not available/configured
        """
        try:
            return TOTPManager.get_user_totp(user_id, broker_name)
        except Exception as e:
            logger.error(f"Error generating user TOTP: {e}")
            return None
    
    @staticmethod
    def validate_totp_secret(secret: str, expected_totp: str) -> bool:
        """
        Validate a TOTP secret by checking if it generates the expected code
        
        Args:
            secret: TOTP secret key
            expected_totp: Expected TOTP code
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            return TOTPManager.validate_totp_secret(secret, expected_totp)
        except Exception as e:
            logger.error(f"Error validating TOTP secret: {e}")
            return False
    
    @staticmethod
    def remove_user_credentials(user_id: str, broker_name: str) -> bool:
        """
        Remove/deactivate user credentials for a broker
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            result = deactivate_user_credentials(user_id, broker_name)
            if result:
                logger.info(f"Successfully removed credentials for user {user_id}, broker {broker_name}")
            else:
                logger.warning(f"No credentials found to remove for user {user_id}, broker {broker_name}")
            return result
        except Exception as e:
            logger.error(f"Error removing user credentials: {e}")
            return False

class BrokerCredentialValidator:
    """Validation utilities for broker credentials"""
    
    # Define required fields for each broker
    BROKER_REQUIREMENTS = {
        'angel': {
            'api_fields': ['api_key', 'api_secret'],
            'user_fields': ['client_id', 'pin'],
            'totp_required': True
        },
        'zebu': {
            'api_fields': ['api_key', 'api_secret'],
            'user_fields': ['user_id_broker', 'password'],
            'totp_required': True  # Can be TOTP/DOB/PAN
        },
        'kotak': {
            'api_fields': ['api_key', 'api_secret'],
            'user_fields': ['mobile_number', 'password'],
            'totp_required': False  # Uses OTP sent to mobile
        },
        'aliceblue': {
            'api_fields': ['api_key', 'api_secret'],
            'user_fields': ['user_id_broker'],
            'totp_required': False  # Uses OAuth flow
        }
        # Add more brokers as needed
    }
    
    @classmethod
    def validate_broker_api_setup(cls, broker_name: str, api_key: str, api_secret: str = None) -> Dict[str, Any]:
        """
        Validate broker API credentials setup
        
        Args:
            broker_name: Name of the broker
            api_key: API key
            api_secret: API secret
            
        Returns:
            Dict with validation results
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        if broker_name not in cls.BROKER_REQUIREMENTS:
            result['valid'] = False
            result['errors'].append(f"Unsupported broker: {broker_name}")
            return result
        
        requirements = cls.BROKER_REQUIREMENTS[broker_name]
        
        # Check required API fields
        if not api_key:
            result['valid'] = False
            result['errors'].append("API key is required")
        
        if 'api_secret' in requirements['api_fields'] and not api_secret:
            result['valid'] = False
            result['errors'].append("API secret is required for this broker")
        
        return result
    
    @classmethod
    def validate_user_credentials_setup(cls, broker_name: str, credentials: Dict, 
                                      totp_option: str, totp_secret: str = None) -> Dict[str, Any]:
        """
        Validate user trading credentials setup
        
        Args:
            broker_name: Name of the broker
            credentials: User credentials dictionary
            totp_option: TOTP option ('manual' or 'stored')
            totp_secret: TOTP secret (if storing)
            
        Returns:
            Dict with validation results
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        if broker_name not in cls.BROKER_REQUIREMENTS:
            result['valid'] = False
            result['errors'].append(f"Unsupported broker: {broker_name}")
            return result
        
        requirements = cls.BROKER_REQUIREMENTS[broker_name]
        
        # Check required user fields
        for field in requirements['user_fields']:
            if not credentials.get(field):
                result['valid'] = False
                result['errors'].append(f"{field} is required for {broker_name}")
        
        # Check TOTP requirements
        if requirements['totp_required']:
            if totp_option == 'stored' and not totp_secret:
                result['valid'] = False
                result['errors'].append("TOTP secret is required when storing TOTP")
            elif totp_option not in ['manual', 'stored']:
                result['valid'] = False
                result['errors'].append("TOTP option must be 'manual' or 'stored'")
        
        # Broker-specific validations
        if broker_name == 'kotak' and credentials.get('mobile_number'):
            mobile = credentials['mobile_number'].replace('+91', '').replace(' ', '')
            if not mobile.isdigit() or len(mobile) != 10:
                result['valid'] = False
                result['errors'].append("Mobile number must be 10 digits")
        
        return result

def get_broker_field_mapping(broker_name: str) -> Dict[str, str]:
    """
    Get field mapping for broker credential forms
    
    Args:
        broker_name: Name of the broker
        
    Returns:
        Dict mapping internal field names to display names
    """
    mappings = {
        'angel': {
            'client_id': 'Client ID',
            'pin': 'PIN',
            'totp': 'TOTP Code'
        },
        'zebu': {
            'user_id_broker': 'User ID',
            'password': 'Password',
            'totp': 'TOTP/DOB/PAN'
        },
        'kotak': {
            'mobile_number': 'Mobile Number',
            'password': 'Password'
        },
        'aliceblue': {
            'user_id_broker': 'User ID'
        }
    }
    
    return mappings.get(broker_name, {})
