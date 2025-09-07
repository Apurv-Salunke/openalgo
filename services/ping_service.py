from typing import Tuple, Dict, Any, Optional
from database.auth_db import get_auth_token_broker
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

def ping_with_auth(auth_token: str, broker: str) -> Tuple[bool, Dict[str, Any], int]:
    """
    Validate auth token and return pong response.
    
    Args:
        auth_token: Authentication token for the broker API
        broker: Name of the broker
        
    Returns:
        Tuple containing:
        - Success status (bool)
        - Response data (dict)
        - HTTP status code (int)
    """
    # Since we've already validated the auth_token by getting here,
    # we can simply return a pong response
    return True, {
        'status': 'success',
        'data': {
            'message': 'pong',
            'broker': broker
        }
    }, 200

def get_ping(api_key: Optional[str] = None, auth_token: Optional[str] = None, broker: Optional[str] = None) -> Tuple[bool, Dict[str, Any], int]:
    """
    Ping endpoint to check API connectivity and authentication.
    Supports both API-based authentication and direct internal calls.
    
    Args:
        api_key: OpenAlgo API key (for API-based calls)
        auth_token: Direct broker authentication token (for internal calls)
        broker: Direct broker name (for internal calls)
        
    Returns:
        Tuple containing:
        - Success status (bool)
        - Response data (dict)
        - HTTP status code (int)
    """
    # Case 1: API-based authentication (when api_key is provided)
    if api_key:
        try:
            from utils.broker_resolver import resolve_broker_and_tokens
            broker_name, AUTH_TOKEN, feed_token = resolve_broker_and_tokens(api_key, broker)
            
            return ping_with_auth(AUTH_TOKEN, broker_name)
            
        except ValueError as e:
            return False, {
                'status': 'error',
                'message': str(e)
            }, 400
        except Exception as e:
            logger.error(f"Error resolving broker and tokens: {e}")
            return False, {
                'status': 'error',
                'message': 'Authentication error'
            }, 500
    
    # Case 2: Direct internal call with auth_token and broker
    elif auth_token and broker:
        return ping_with_auth(auth_token, broker)
    
    # Case 3: Invalid parameters
    else:
        return False, {
            'status': 'error',
            'message': 'Either api_key or both auth_token and broker must be provided'
        }, 400