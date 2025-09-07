# restx_api/broker_credentials.py

"""
Single API for broker credential management in single-user multi-broker system.

One endpoint to:
1. Store complete broker credentials (API + trading credentials)
2. Validate credentials with the actual broker
3. Return success/failure with validation details
"""

from flask_restx import Namespace, Resource, fields
from flask import request
from utils.credential_manager import CredentialManager
from utils.logging import get_logger
from database.auth_db import verify_api_key
from services.broker_auth_service import BrokerAuthService

logger = get_logger(__name__)

# Create namespace
broker_creds_ns = Namespace('broker-credentials', description='Single API for broker credential management')

# Complete broker setup model
broker_setup_model = broker_creds_ns.model('BrokerSetup', {
    'broker_name': fields.String(required=True, description='Broker name (e.g., angel, zebu, kotak)'),
    # Broker API credentials
    'api_key': fields.String(required=True, description='Broker API key'),
    'api_secret': fields.String(description='Broker API secret (if required)'),
    # User trading credentials
    'client_id': fields.String(description='Client ID'),
    'user_id_broker': fields.String(description='User ID for broker'),
    'mobile_number': fields.String(description='Mobile number'),
    'password': fields.String(description='Trading password'),
    'pin': fields.String(description='Trading PIN'),
    'totp_option': fields.String(required=True, description='TOTP option: manual or stored', enum=['manual', 'stored']),
    'totp_secret': fields.String(description='TOTP secret key (required if totp_option=stored)')
})

# Response model
setup_response_model = broker_creds_ns.model('SetupResponse', {
    'success': fields.Boolean(description='Whether setup was successful'),
    'message': fields.String(description='Success/error message'),
    'broker_name': fields.String(description='Broker name'),
    'validation_passed': fields.Boolean(description='Whether broker validation passed'),
    'auth_token': fields.String(description='Authentication token if successful')
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

@broker_creds_ns.route('/setup')
class BrokerSetup(Resource):
    @broker_creds_ns.expect(broker_setup_model)
    @broker_creds_ns.marshal_with(setup_response_model)
    @broker_creds_ns.doc('setup_broker')
    @require_api_key
    def post(self):
        """
        Complete broker setup: Store credentials and validate with broker
        
        This single API:
        1. Stores broker API credentials
        2. Stores user trading credentials  
        3. Validates credentials by attempting broker authentication
        4. Returns success/failure with validation details
        """
        try:
            data = request.get_json()
            user_id = request.user_id
            
            broker_name = data.get('broker_name')
            if not broker_name:
                return {
                    'success': False,
                    'message': 'broker_name is required',
                    'validation_passed': False
                }, 400
            
            # Extract all credentials
            api_key = data.get('api_key')
            api_secret = data.get('api_secret')
            
            if not api_key:
                return {
                    'success': False,
                    'message': 'api_key is required',
                    'validation_passed': False
                }, 400
            
            # Extract trading credentials
            trading_creds = {}
            for field in ['client_id', 'user_id_broker', 'mobile_number', 'password', 'pin']:
                if data.get(field):
                    trading_creds[field] = data[field]
            
            totp_option = data.get('totp_option', 'manual')
            totp_secret = data.get('totp_secret')
            
            # Validate TOTP setup
            if totp_option == 'stored' and not totp_secret:
                return {
                    'success': False,
                    'message': 'totp_secret is required when totp_option=stored',
                    'validation_passed': False
                }, 400
            
            logger.info(f"Setting up broker credentials for {broker_name}")
            
            # Step 1: Store broker API credentials
            api_success = CredentialManager.setup_broker_api(
                broker_name=broker_name,
                api_key=api_key,
                api_secret=api_secret
            )
            
            if not api_success:
                return {
                    'success': False,
                    'message': 'Failed to store broker API credentials',
                    'validation_passed': False
                }, 500
            
            # Step 2: Store user trading credentials
            user_success = CredentialManager.setup_user_credentials(
                user_id=user_id,
                broker_name=broker_name,
                credentials=trading_creds,
                totp_option=totp_option,
                totp_secret=totp_secret
            )
            
            if not user_success:
                return {
                    'success': False,
                    'message': 'Failed to store user trading credentials',
                    'validation_passed': False
                }, 500
            
            # Step 3: Validate credentials by attempting authentication
            logger.info(f"Validating credentials with {broker_name}")
            
            auth_result = BrokerAuthService.authenticate_user_with_broker(
                user_id=user_id,
                broker_name=broker_name,
                totp_code=None  # Use stored TOTP if available
            )
            
            if auth_result['success']:
                # Store auth token in existing system
                auth_token = auth_result.get('auth_token')
                feed_token = auth_result.get('feed_token')
                broker_user_id = auth_result.get('user_id')
                
                # Authentication successful - tokens already stored by BrokerAuthService
                # No need to trigger master contract download for API setup
                logger.info(f"Successfully set up and validated {broker_name} for user {user_id}")
                
                return {
                        'success': True,
                        'message': f'Successfully configured and validated {broker_name} credentials',
                        'broker_name': broker_name,
                        'validation_passed': True,
                        'auth_token': auth_token
                    }
            
            # Authentication failed - credentials are stored but not validated
            error_msg = auth_result.get('error', 'Credential validation failed')
            logger.warning(f"Credentials stored but validation failed for {broker_name}: {error_msg}")
            
            return {
                'success': False,
                'message': f'Credentials stored but validation failed: {error_msg}',
                'broker_name': broker_name,
                'validation_passed': False
            }, 400
            
        except Exception as e:
            logger.error(f"Error in broker setup: {e}")
            return {
                'success': False,
                'message': f'Server error: {str(e)}',
                'validation_passed': False
            }, 500

@broker_creds_ns.route('/list')
class BrokerList(Resource):
    @broker_creds_ns.doc('list_configured_brokers')
    @require_api_key
    def get(self):
        """List all configured brokers for the user"""
        try:
            user_id = request.user_id
            
            # Get brokers with both API and user credentials configured
            configured_brokers = CredentialManager.list_configured_brokers()
            user_brokers = CredentialManager.get_user_broker_list(user_id)
            
            # Find brokers that have both API and user credentials
            complete_brokers = []
            user_broker_names = {broker['broker_name'] for broker in user_brokers}
            
            for broker in configured_brokers:
                broker_name = broker['broker_name']
                if broker_name in user_broker_names:
                    # Get TOTP option for this broker
                    totp_option = next(
                        (b['totp_option'] for b in user_brokers if b['broker_name'] == broker_name),
                        'manual'
                    )
                    complete_brokers.append({
                        'broker_name': broker_name,
                        'totp_option': totp_option,
                        'configured_at': broker.get('created_at')
                    })
            
            return {
                'success': True,
                'brokers': complete_brokers,
                'count': len(complete_brokers)
            }
            
        except Exception as e:
            logger.error(f"Error listing brokers: {e}")
            return {'error': f'Server error: {str(e)}'}, 500
