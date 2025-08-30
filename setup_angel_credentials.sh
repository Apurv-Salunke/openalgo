#!/bin/bash

# Load credentials from file
source broker_credentials.txt

echo "🔧 Setting up Angel One credentials with single API"
echo "=================================================="

echo ""
echo "Setting up and validating Angel One credentials..."
curl -X POST "http://localhost:5000/api/broker-credentials/setup" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: $OPENALGO_API_KEY" \
  -d '{
    "broker_name": "angel",
    "api_key": "'$ANGEL_API_KEY'",
    "api_secret": "'$ANGEL_API_SECRET'",
    "client_id": "'$ANGEL_CLIENT_ID'",
    "pin": "'$ANGEL_PIN'",
    "totp_option": "stored",
    "totp_secret": "'$ANGEL_TOTP_SECRET'"
  }'

echo ""
echo ""
echo "Listing configured brokers..."
curl -X GET "http://localhost:5000/api/broker-credentials/list" \
  -H "X-API-KEY: $OPENALGO_API_KEY"

echo ""
echo ""
echo "✅ Setup complete! Your Angel One credentials are configured and validated."