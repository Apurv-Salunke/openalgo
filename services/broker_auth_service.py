# services/broker_auth_service.py

"""
Broker authentication service for OpenAlgo multi-broker system.

This service handles the authentication flow using the new dual credential system,
combining broker API credentials with user trading credentials.
"""

import os
from typing import Dict, Optional, Tuple, Any
from utils.credential_manager import CredentialManager
from utils.logging import get_logger

logger = get_logger(__name__)

class BrokerAuthService:
    """Service for handling broker authentication with dual credentials"""
    
    @staticmethod
    def authenticate_user_with_broker(user_id: str, broker_name: str, 
                                    totp_code: str = None) -> Dict[str, Any]:
        """
        Authenticate user with broker using stored credentials
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            totp_code: TOTP code (required for manual TOTP option)
            
        Returns:
            Dict with authentication result
        """
        try:
            logger.info(f"Starting authentication for user {user_id} with broker {broker_name}")
            
            # Get combined credentials
            combined_creds = CredentialManager.get_authentication_credentials(user_id, broker_name)
            if not combined_creds:
                return {
                    'success': False,
                    'error': 'No credentials configured for this broker',
                    'error_code': 'NO_CREDENTIALS'
                }
            
            broker_api = combined_creds['broker_api']
            user_trading = combined_creds['user_trading']
            
            # Handle TOTP based on user preference
            final_totp = None
            if user_trading['totp_option'] == 'stored':
                # Generate TOTP from stored secret
                final_totp = CredentialManager.generate_user_totp(user_id, broker_name)
                if not final_totp:
                    return {
                        'success': False,
                        'error': 'Failed to generate TOTP from stored secret',
                        'error_code': 'TOTP_GENERATION_FAILED'
                    }
                logger.info(f"Generated TOTP from stored secret for user {user_id}")
            else:
                # Use provided TOTP code
                if not totp_code:
                    return {
                        'success': False,
                        'error': 'TOTP code required for manual TOTP option',
                        'error_code': 'TOTP_REQUIRED'
                    }
                final_totp = totp_code
                logger.info(f"Using provided TOTP code for user {user_id}")
            
            # Call broker-specific authentication function
            auth_result = BrokerAuthService._call_broker_auth_function(
                broker_name=broker_name,
                broker_api_creds=broker_api,
                user_trading_creds=user_trading,
                totp_code=final_totp
            )
            
            if auth_result['success']:
                logger.info(f"Successfully authenticated user {user_id} with broker {broker_name}")
            else:
                logger.warning(f"Authentication failed for user {user_id} with broker {broker_name}: {auth_result.get('error')}")
            
            return auth_result
            
        except Exception as e:
            logger.error(f"Error during broker authentication: {e}")
            return {
                'success': False,
                'error': f'Authentication error: {str(e)}',
                'error_code': 'AUTHENTICATION_ERROR'
            }
    
    @staticmethod
    def _call_broker_auth_function(broker_name: str, broker_api_creds: Dict, 
                                 user_trading_creds: Dict, totp_code: str) -> Dict[str, Any]:
        """
        Call the appropriate broker authentication function
        
        Args:
            broker_name: Name of the broker
            broker_api_creds: Broker API credentials
            user_trading_creds: User trading credentials
            totp_code: TOTP code
            
        Returns:
            Dict with authentication result
        """
        try:
            # Import the specific broker authentication module
            broker_module = f"broker.{broker_name}.api.auth_api"
            
            try:
                import importlib
                auth_module = importlib.import_module(broker_module)
            except ImportError:
                logger.error(f"Could not import authentication module for broker: {broker_name}")
                return {
                    'success': False,
                    'error': f'Broker {broker_name} not supported',
                    'error_code': 'BROKER_NOT_SUPPORTED'
                }
            
            # Prepare authentication parameters based on broker
            auth_params = BrokerAuthService._prepare_auth_params(
                broker_name, broker_api_creds, user_trading_creds, totp_code
            )
            
            # Call the broker's authentication function
            if hasattr(auth_module, 'authenticate'):
                result = auth_module.authenticate(**auth_params)
                return BrokerAuthService._process_auth_result(result)
            else:
                logger.error(f"Authentication function not found for broker: {broker_name}")
                return {
                    'success': False,
                    'error': f'Authentication function not implemented for {broker_name}',
                    'error_code': 'AUTH_FUNCTION_MISSING'
                }
                
        except Exception as e:
            logger.error(f"Error calling broker authentication function: {e}")
            return {
                'success': False,
                'error': f'Broker authentication error: {str(e)}',
                'error_code': 'BROKER_AUTH_ERROR'
            }
    
    @staticmethod
    def _prepare_auth_params(broker_name: str, broker_api_creds: Dict, 
                           user_trading_creds: Dict, totp_code: str) -> Dict[str, Any]:
        """
        Prepare authentication parameters for specific broker
        
        Args:
            broker_name: Name of the broker
            broker_api_creds: Broker API credentials
            user_trading_creds: User trading credentials
            totp_code: TOTP code
            
        Returns:
            Dict with broker-specific authentication parameters
        """
        base_params = {
            'api_key': broker_api_creds['api_key'],
            'api_secret': broker_api_creds.get('api_secret'),
            'totp': totp_code
        }
        
        # Add broker-specific parameters
        if broker_name == 'angel':
            base_params.update({
                'clientcode': user_trading_creds['client_id'],
                'password': user_trading_creds['pin']
            })
        elif broker_name == 'zebu':
            base_params.update({
                'userid': user_trading_creds['user_id_broker'],
                'password': user_trading_creds['password']
            })
        elif broker_name == 'kotak':
            base_params.update({
                'mobilenumber': user_trading_creds['mobile_number'],
                'password': user_trading_creds['password']
            })
        elif broker_name == 'aliceblue':
            base_params.update({
                'userid': user_trading_creds['user_id_broker']
            })
        
        return base_params
    
    @staticmethod
    def _process_auth_result(result: Any) -> Dict[str, Any]:
        """
        Process and standardize broker authentication result
        
        Args:
            result: Raw result from broker authentication
            
        Returns:
            Standardized authentication result
        """
        try:
            # Handle different result formats from different brokers
            if isinstance(result, dict):
                if result.get('status') == 'success' or result.get('success') is True:
                    return {
                        'success': True,
                        'auth_token': result.get('auth_token') or result.get('token'),
                        'feed_token': result.get('feed_token'),
                        'user_id': result.get('user_id'),
                        'broker_user_id': result.get('broker_user_id'),
                        'additional_data': result.get('additional_data', {})
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('message') or result.get('error') or 'Authentication failed',
                        'error_code': result.get('error_code', 'AUTH_FAILED')
                    }
            elif isinstance(result, tuple):
                # Handle tuple results (token, status) or (token, feed_token, status)
                if len(result) >= 2 and result[-1]:  # Last element is success status
                    return {
                        'success': True,
                        'auth_token': result[0],
                        'feed_token': result[1] if len(result) > 2 else None
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Authentication failed',
                        'error_code': 'AUTH_FAILED'
                    }
            else:
                # Handle simple boolean or string results
                if result:
                    return {
                        'success': True,
                        'auth_token': str(result) if not isinstance(result, bool) else None
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Authentication failed',
                        'error_code': 'AUTH_FAILED'
                    }
                    
        except Exception as e:
            logger.error(f"Error processing authentication result: {e}")
            return {
                'success': False,
                'error': f'Error processing authentication result: {str(e)}',
                'error_code': 'RESULT_PROCESSING_ERROR'
            }
    
    @staticmethod
    def test_broker_credentials(user_id: str, broker_name: str, 
                              credentials: Dict, totp_code: str = None) -> Dict[str, Any]:
        """
        Test broker credentials without storing them
        
        Args:
            user_id: User identifier
            broker_name: Name of the broker
            credentials: User credentials to test
            totp_code: TOTP code for testing
            
        Returns:
            Dict with test result
        """
        try:
            logger.info(f"Testing credentials for user {user_id} with broker {broker_name}")
            
            # Get broker API credentials
            broker_api_creds = CredentialManager.get_broker_api(broker_name)
            if not broker_api_creds:
                return {
                    'success': False,
                    'error': f'No API credentials configured for broker {broker_name}',
                    'error_code': 'NO_BROKER_API_CREDS'
                }
            
            # Prepare test parameters
            auth_params = BrokerAuthService._prepare_auth_params(
                broker_name, broker_api_creds, credentials, totp_code
            )
            
            # Call broker authentication
            auth_result = BrokerAuthService._call_broker_auth_function(
                broker_name, broker_api_creds, credentials, totp_code
            )
            
            if auth_result['success']:
                logger.info(f"Credential test successful for user {user_id} with broker {broker_name}")
            else:
                logger.warning(f"Credential test failed for user {user_id} with broker {broker_name}")
            
            return auth_result
            
        except Exception as e:
            logger.error(f"Error testing broker credentials: {e}")
            return {
                'success': False,
                'error': f'Credential test error: {str(e)}',
                'error_code': 'CREDENTIAL_TEST_ERROR'
            }
    
    @staticmethod
    def get_user_auth_status(user_id: str) -> Dict[str, Any]:
        """
        Get authentication status for all user's configured brokers
        
        Args:
            user_id: User identifier
            
        Returns:
            Dict with authentication status for each broker
        """
        try:
            user_brokers = CredentialManager.get_user_broker_list(user_id)
            auth_status = {}
            
            for broker_info in user_brokers:
                broker_name = broker_info['broker_name']
                
                # Check if broker API credentials are available
                broker_api_available = CredentialManager.get_broker_api(broker_name) is not None
                
                auth_status[broker_name] = {
                    'user_credentials_configured': True,
                    'broker_api_configured': broker_api_available,
                    'totp_option': broker_info['totp_option'],
                    'ready_for_auth': broker_api_available,
                    'configured_at': broker_info['created_at']
                }
            
            return {
                'success': True,
                'auth_status': auth_status,
                'total_brokers': len(user_brokers)
            }
            
        except Exception as e:
            logger.error(f"Error getting user auth status: {e}")
            return {
                'success': False,
                'error': f'Error getting auth status: {str(e)}',
                'error_code': 'AUTH_STATUS_ERROR'
            }

# Backward compatibility functions for existing code
def authenticate_with_stored_credentials(user_id: str, broker_name: str, totp_code: str = None):
    """
    Backward compatibility function for existing authentication calls
    
    Args:
        user_id: User identifier
        broker_name: Name of the broker
        totp_code: TOTP code (optional, depends on user's TOTP setting)
        
    Returns:
        Authentication result in the format expected by existing code
    """
    result = BrokerAuthService.authenticate_user_with_broker(user_id, broker_name, totp_code)
    
    if result['success']:
        return result.get('auth_token'), result.get('feed_token'), True
    else:
        return None, None, False
