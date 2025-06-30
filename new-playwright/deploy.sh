#!/bin/bash
# deploy.sh - Deploy FAQ Scraper Lambda function using Docker container
# Usage: ./deploy.sh --region us-east-1 --account 304598107598 --profile access-role

set -e

# Default Configuration
FUNCTION_NAME="scraper-with-playwright"
REPOSITORY_NAME="scraper-with-playwright-repo"
RUNTIME="python3.13"
TIMEOUT=400
MEMORY=3008
ROLE_NAME="sanjay-platform-role"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
REGION="us-east-1"
ACCOUNT="304598107598"
PROFILE="access-role"

# Function to display usage
usage() {
    echo "Usage: $0 --region REGION --account ACCOUNT --profile PROFILE [OPTIONS]"
    echo ""
    echo "Required Parameters:"
    echo "  --region REGION          AWS region (e.g., us-east-1)"
    echo "  --account ACCOUNT        AWS account ID (12-digit number)"
    echo "  --profile PROFILE        AWS CLI profile name"
    echo ""
    echo "Optional Parameters:"
    echo "  --function-name NAME     Lambda function name (default: $FUNCTION_NAME)"
    echo "  --repository-name NAME   ECR repository name (default: $REPOSITORY_NAME)"
    echo "  --role-name NAME         IAM role name (default: $ROLE_NAME)"
    echo "  --timeout SECONDS        Function timeout (default: $TIMEOUT)"
    echo "  --memory MB              Memory allocation (default: $MEMORY)"
    echo "  --help                   Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --region us-east-1 --account 304598107598 --profile access-role"
}

echo_info() {
    echo -e "${GREEN}ℹ️  $1${NC}"
}

echo_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo_step() {
    echo -e "${BLUE}🔄 $1${NC}"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --account)
            ACCOUNT="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --function-name)
            FUNCTION_NAME="$2"
            shift 2
            ;;
        --repository-name)
            REPOSITORY_NAME="$2"
            shift 2
            ;;
        --role-name)
            ROLE_NAME="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --memory)
            MEMORY="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo_error "Unknown parameter: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$REGION" || -z "$ACCOUNT" || -z "$PROFILE" ]]; then
    echo_error "Missing required parameters"
    usage
    exit 1
fi

# Set AWS CLI parameters
AWS_CMD="aws --profile $PROFILE --region $REGION"

echo_info "🚀 FAQ Scraper Docker Deployment"
echo "====================================="
echo_info "Function Name: $FUNCTION_NAME"
echo_info "ECR Repository: $REPOSITORY_NAME"
echo_info "Region: $REGION"
echo_info "Account: $ACCOUNT"
echo_info "Profile: $PROFILE"
echo_info "Role Name: $ROLE_NAME"
echo "====================================="

# Step 1: Validate AWS CLI and Profile
echo_step "Step 1: Validating AWS Configuration"

if ! $AWS_CMD sts get-caller-identity &>/dev/null; then
    echo_error "AWS CLI not configured properly or profile '$PROFILE' not found"
    echo "Please check your AWS CLI configuration and profile"
    exit 1
fi

CURRENT_ACCOUNT=$($AWS_CMD sts get-caller-identity --query 'Account' --output text)
if [[ "$CURRENT_ACCOUNT" != "$ACCOUNT" ]]; then
    echo_error "Account mismatch! Expected: $ACCOUNT, Got: $CURRENT_ACCOUNT"
    exit 1
fi

echo_info "AWS CLI configured correctly ✅"

# Step 2: Validate IAM Role
echo_step "Step 2: Validating IAM Role"

ROLE_ARN="arn:aws:iam::$ACCOUNT:role/$ROLE_NAME"

if ! $AWS_CMD iam get-role --role-name $ROLE_NAME &>/dev/null; then
    echo_error "Role '$ROLE_NAME' not found in account $ACCOUNT"
    echo "Please ensure the role exists with Lambda execution permissions"
    exit 1
fi

echo_info "IAM Role validated: $ROLE_ARN ✅"

# Step 3: Create or Validate ECR Repository
echo_step "Step 3: Setting up ECR Repository"

REPO_URI="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME"

if ! $AWS_CMD ecr describe-repositories --repository-names $REPOSITORY_NAME &>/dev/null; then
    echo_info "Creating ECR repository: $REPOSITORY_NAME"
    $AWS_CMD ecr create-repository --repository-name $REPOSITORY_NAME >/dev/null
    echo_info "ECR repository created: $REPO_URI"
else
    echo_info "Using existing ECR repository: $REPO_URI"
fi

# Step 4: Build and Push Docker Image
echo_step "Step 4: Building and Pushing Docker Image"

# Ensure Dockerfile exists
if [[ ! -f "Dockerfile" ]]; then
    echo_error "Dockerfile not found in current directory"
    exit 1
fi

# # Ensure main.py exists
# if [[ ! -f "main.py" ]]; then
#     echo_error "main.py not found in current directory"
#     exit 1
# fi

# Log in to ECR
echo_info "Logging in to Amazon ECR..."
$AWS_CMD ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

# Build Docker image
echo_info "Building Docker image..."
docker buildx build --platform linux/amd64 --provenance=false -t $REPOSITORY_NAME:latest .

# Tag and push Docker image
echo_info "Tagging and pushing image to ECR..."
docker tag $REPOSITORY_NAME:latest $REPO_URI:latest
docker push $REPO_URI:latest

echo_info "Docker image pushed successfully ✅"

# Step 5: Deploy or Update Lambda Function
echo_step "Step 5: Deploying Lambda Function"

# Check if function exists
if $AWS_CMD lambda get-function --function-name $FUNCTION_NAME &>/dev/null; then
    echo_warning "Function $FUNCTION_NAME already exists, updating..."
    
    # Update function code
    $AWS_CMD lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --image-uri $REPO_URI:latest >/dev/null
    
    # Wait for code update
    echo_info "Waiting for function update..."
    $AWS_CMD lambda wait function-updated --function-name $FUNCTION_NAME
    
    # Update configuration
    $AWS_CMD lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --timeout $TIMEOUT \
        --memory-size $MEMORY \
        --role $ROLE_ARN \
        --environment "Variables={CHROME_BINARY=/opt/chrome/chrome-linux64/chrome,CHROMEDRIVER_PATH=/opt/chrome-driver/chromedriver-linux64/chromedriver}" >/dev/null
else
    echo_info "Creating new Lambda function..."
    
    # Create new function
    $AWS_CMD lambda create-function \
        --function-name $FUNCTION_NAME \
        --package-type Image \
        --code ImageUri=$REPO_URI:latest \
        --role $ROLE_ARN \
        --timeout $TIMEOUT \
        --memory-size $MEMORY \
        --environment "Variables={CHROME_BINARY=/opt/chrome/chrome-linux64/chrome,CHROMEDRIVER_PATH=/opt/chrome-driver/chromedriver-linux64/chromedriver}" >/dev/null
fi

echo_info "Lambda function deployed successfully ✅"

echo ""
echo_info "🎉 Deployment Complete!"
echo "==========================================="
echo_info "Function Name: $FUNCTION_NAME"
echo_info "Function ARN: arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNCTION_NAME"
echo_info "ECR Repository: $REPO_URI"
echo_info "Role: $ROLE_ARN"
echo "==========================================="