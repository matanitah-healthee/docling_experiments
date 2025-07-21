# AWS Textract Setup Guide

## Prerequisites
To use Amazon Textract comparison feature, you need:

1. **AWS Account** - Sign up at https://aws.amazon.com/
2. **AWS Credentials** - Configure using one of these methods:

### Method 1: AWS CLI (Recommended)
```bash
# Install AWS CLI
brew install awscli  # macOS
# or pip install awscli

# Configure credentials
aws configure
```

### Method 2: Environment Variables
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1  # or your preferred region
```

### Method 3: Create ~/.aws/credentials file
```ini
[default]
aws_access_key_id = your_access_key
aws_secret_access_key = your_secret_key
region = us-east-1
```

## Getting AWS Credentials
1. Go to AWS Console → IAM → Users → Your User
2. Security credentials tab
3. Create access key → Download .csv file
4. Use the Access Key ID and Secret Access Key

## Required Permissions
Your AWS user needs these permissions:
- `textract:AnalyzeDocument`

## Testing
Run the script to test both Docling and Textract:
```bash
python main.py
```

## Costs
Amazon Textract charges per page analyzed (~$0.05-0.15 per page depending on features used).
The sample documents in this script should cost less than $1 total.

## Disable Textract
To disable Textract comparison, set in main.py:
```python
COMPARE_WITH_TEXTRACT = False
``` 