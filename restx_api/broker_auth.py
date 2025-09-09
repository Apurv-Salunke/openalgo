# restx_api/broker_auth.py

"""
Broker authentication API for API-only flow.
"""

from flask_restx import Namespace, Resource, fields
from flask import request
from utils.logging import get_logger
from database.auth_db import verify_api_key, get_auth_token_by_broker
from services.broker_auth_service import BrokerAuthService
from utils.credential_manager import CredentialManager

logger = get_logger(__name__)

# Create namespace
broker_auth_ns = Namespace('broker-auth', description='Broker authentication APIs')

# Authentication request model
auth_request_model = broker_auth_ns.model('AuthRequest', {
    'broker_name': fields.String(required=True, description='Broker name (e.g., angel, zebu)'),
    'totp_code': fields.String(description='TOTP code (required for manual TOTP, optional for automatic)')
})

# Authentication response model
auth_response_model = broker_auth_ns.model('AuthResponse', {
    'success': fields.Boolean(description='Whether authentication was successful'),
    'message': fields.String(description='Success/error message'),
    'broker_name': fields.String(description='Broker name'),
    'auth_token': fields.String(description='Authentication token if successful'),
    'feed_token': fields.String(description='Feed token if available'),
    'token_source': fields.String(description='Source of token: new_authentication')
})

def require_api_key(f):
    """Decorator to require valid API key"""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-KEY')
        if not api_key:
            return {'error': 'API key required'}, 401
        
        user_id = verify_api_key(api_key)
        if not user_id:
            return {'error': 'Invalid API key'}, 401
        
        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated_function

def is_token_valid(auth_token):
    """Check if auth token is valid (not expired/revoked)"""
    # For now, we'll consider tokens valid if they exist
    # In a real implementation, you might check expiration, revocation status, etc.
    return auth_token is not None and auth_token.strip() != ''

@broker_auth_ns.route('/authenticate')
class BrokerAuthenticate(Resource):
    @broker_auth_ns.expect(auth_request_model)
    @broker_auth_ns.marshal_with(auth_response_model)
    @broker_auth_ns.doc('authenticate_broker')
    @require_api_key
    def post(self):
        """
        Authenticate with a configured broker
        
        This API always performs a fresh authentication against the broker,
        regardless of any existing stored tokens.
        - Uses stored TOTP for automatic mode, provided TOTP for manual mode
        - Stores new tokens if authentication succeeds
        """
        try:
            data = request.get_json()
            user_id = request.user_id
            
            broker_name = data.get('broker_name')
            totp_code = data.get('totp_code')
            
            if not broker_name:
                return {
                    'success': False,
                    'message': 'broker_name is required',
                    'broker_name': None,
                    'auth_token': None,
                    'token_source': None
                }, 400
            
            logger.info(f"Authenticating user {user_id} with broker {broker_name}")
            
            # Step 1: Check if broker is configured
            user_creds = CredentialManager.get_user_credentials(user_id, broker_name)
            if not user_creds:
                return {
                    'success': False,
                    'message': f'Broker {broker_name} not configured for this user. Use /broker-credentials/setup first.',
                    'broker_name': broker_name,
                    'auth_token': None,
                    'token_source': None
                }, 400
            
            # Step 2: Check if broker API credentials are available
            broker_api_creds = CredentialManager.get_broker_api(broker_name)
            if not broker_api_creds:
                return {
                    'success': False,
                    'message': f'Broker API credentials not configured for {broker_name}',
                    'broker_name': broker_name,
                    'auth_token': None,
                    'token_source': None
                }, 400
            
            # Step 3: Determine TOTP method and authenticate (always fresh auth)
            totp_option = user_creds.get('totp_option', 'manual')
            
            if totp_option == 'automatic':
                # Use stored TOTP secret
                logger.info(f"Using automatic TOTP for user {user_id} with broker {broker_name}")
                auth_result = BrokerAuthService.authenticate_user_with_broker(
                    user_id=user_id,
                    broker_name=broker_name,
                    totp_code=None  # Use stored TOTP
                )
            else:
                # Use provided TOTP code
                if not totp_code:
                    return {
                        'success': False,
                        'message': 'TOTP code required for manual authentication',
                        'broker_name': broker_name,
                        'auth_token': None,
                        'token_source': None
                    }, 400
                
                logger.info(f"Using manual TOTP for user {user_id} with broker {broker_name}")
                auth_result = BrokerAuthService.authenticate_user_with_broker(
                    user_id=user_id,
                    broker_name=broker_name,
                    totp_code=totp_code
                )
            
            # Step 4: Handle authentication result
            if auth_result['success']:
                auth_token = auth_result.get('auth_token')
                feed_token = auth_result.get('feed_token')
                
                logger.info(f"Successfully authenticated user {user_id} with broker {broker_name}")
                
                return {
                    'success': True,
                    'message': f'Successfully authenticated with {broker_name}',
                    'broker_name': broker_name,
                    'auth_token': auth_token,
                    'feed_token': feed_token,
                    'token_source': 'new_authentication'
                }
            else:
                error_msg = auth_result.get('error', 'Authentication failed')
                logger.warning(f"Authentication failed for user {user_id} with broker {broker_name}: {error_msg}")
                
                return {
                    'success': False,
                    'message': f'Authentication failed: {error_msg}',
                    'broker_name': broker_name,
                    'auth_token': None,
                    'token_source': None
                }, 400
            
        except Exception as e:
            logger.error(f"Error in broker authentication: {e}")
            return {
                'success': False,
                'message': f'Server error: {str(e)}',
                'broker_name': broker_name if 'broker_name' in locals() else None,
                'auth_token': None,
                'token_source': None
            }, 500
