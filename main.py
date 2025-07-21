# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "docling-core",
#     "mlx-vlm",
#     "pillow",
#     "boto3",
#     "python-dotenv",
#     "pymupdf",
# ]
# ///
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import json
import os

import requests
import boto3
import fitz  # PyMuPDF
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from botocore.exceptions import NoCredentialsError
from PIL import Image
from docling_core.types.doc.base import ImageRefMode
from docling_core.types.doc.document import DocTagsDocument, DoclingDocument
from mlx_vlm import load, generate, stream_generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

## Settings (loaded from environment variables)
SHOW_IN_BROWSER = os.getenv('SHOW_IN_BROWSER', 'true').lower() == 'true'
COMPARE_WITH_TEXTRACT = os.getenv('COMPARE_WITH_TEXTRACT', 'true').lower() == 'true'
AWS_PROFILE = os.getenv('AWS_PROFILE', 'ds')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
MODEL_PATH = os.getenv('MODEL_PATH', 'ds4sd/SmolDocling-256M-preview-mlx-bf16')
IMAGE_URL = os.getenv('IMAGE_URL', 'https://www.cigna.com/static/www-cigna-com/docs/ifp/m-25-sbc-co-945220-b-connectflex9200rx.pdf')
OUTPUT_HTML_PATH = os.getenv('OUTPUT_HTML_PATH', './output.html')
COMPARISON_OUTPUT_PATH = os.getenv('COMPARISON_OUTPUT_PATH', './comparison_output.txt')

## Textract Functions
def analyze_document_with_textract(image_bytes):
    """Analyze document using Amazon Textract"""
    try:
        # Try to use the configured AWS profile first
        try:
            session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
            textract = session.client('textract')
            print(f"Using AWS profile '{AWS_PROFILE}' in region '{AWS_REGION}'")
        except Exception:
            # Fallback to default credentials
            textract = boto3.client('textract', region_name=AWS_REGION)
            print(f"Using default AWS credentials in region '{AWS_REGION}'")
        
        # Call Textract to analyze the document
        response = textract.analyze_document(
            Document={'Bytes': image_bytes},
            FeatureTypes=['TABLES', 'FORMS']
        )
        
        return response
    except NoCredentialsError:
        print("Error: AWS credentials not found.")
        print("Please run 'aws sso login' to refresh your SSO session, or configure credentials:")
        print("1. Run 'aws configure sso' for SSO setup")
        print("2. Run 'aws configure' for access keys")
        print("3. Set environment variables: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        return None
    except Exception as e:
        if "security token" in str(e).lower() or "invalid" in str(e).lower():
            print(f"Error: AWS credentials are expired or invalid.")
            print("Please run 'aws sso login' to refresh your SSO session.")
        else:
            print(f"Error with Textract: {e}")
        return None

def extract_text_from_textract(response):
    """Extract text and tables from Textract response"""
    if not response:
        return "Textract analysis failed - check AWS credentials"
    
    blocks = response['Blocks']
    
    # Extract lines of text
    lines = []
    tables = []
    
    for block in blocks:
        if block['BlockType'] == 'LINE':
            lines.append(block['Text'])
        elif block['BlockType'] == 'TABLE':
            tables.append(block)
    
    # Build text output
    text_output = "\n".join(lines)
    
    # Extract table information
    table_output = ""
    if tables:
        table_output = f"\n\nTables detected: {len(tables)}\n"
        for i, table in enumerate(tables):
            table_output += f"Table {i+1}: {table.get('Confidence', 'N/A')}% confidence\n"
    
    return f"=== AMAZON TEXTRACT OUTPUT ===\n\n{text_output}{table_output}"

def format_comparison(docling_output, textract_output):
    """Format both outputs for comparison"""
    separator = "=" * 80
    comparison = f"""
{separator}
                           DOCLING vs TEXTRACT COMPARISON
{separator}

=== DOCLING OUTPUT ===

{docling_output}

{separator}

{textract_output}

{separator}
"""
    return comparison

## Load the model
model, processor = load(MODEL_PATH)
config = load_config(MODEL_PATH)

## Prepare input
prompt = "Convert this page to docling."

# Use image URL from environment variable
image_url = IMAGE_URL

# Load image resource
def load_document_as_image(url_or_path):
    """Load document (PDF or image) and convert to PIL Image"""
    if urlparse(url_or_path).scheme != "":  # it is a URL
        response = requests.get(url_or_path, stream=True, timeout=10)
        response.raise_for_status()
        content_bytes = response.content
        
        # Check if it's a PDF by URL extension or content
        is_pdf = (url_or_path.lower().endswith('.pdf') or 
                 response.headers.get('content-type', '').lower() == 'application/pdf')
    else:
        with open(url_or_path, 'rb') as f:
            content_bytes = f.read()
        is_pdf = url_or_path.lower().endswith('.pdf')
    
    if is_pdf:
        # Convert PDF first page to image using PyMuPDF
        pdf_doc = fitz.open(stream=content_bytes, filetype="pdf")
        first_page = pdf_doc[0]
        # Render page to image (higher DPI for better quality)
        pix = first_page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))  # 2x scaling for better quality
        img_data = pix.tobytes("png")
        pdf_doc.close()
        
        # Create PIL image from PNG bytes
        pil_image = Image.open(BytesIO(img_data))
        image_bytes = img_data  # Use the PNG bytes for Textract
    else:
        # Regular image file
        pil_image = Image.open(BytesIO(content_bytes))
        image_bytes = content_bytes
    
    return pil_image, image_bytes

pil_image, image_bytes = load_document_as_image(image_url)

# Analyze with Textract (if enabled)
textract_output = None
if COMPARE_WITH_TEXTRACT:
    print("Analyzing with Amazon Textract...")
    textract_response = analyze_document_with_textract(image_bytes)
    textract_output = extract_text_from_textract(textract_response)
    print("Textract analysis complete.\n")

# Apply chat template
formatted_prompt = apply_chat_template(processor, config, prompt, num_images=1)

## Generate output
print("DocTags: \n\n")

output = ""
try:
    # Use generate instead of stream_generate to avoid type issues
    result = generate(
        model, processor, formatted_prompt, pil_image, max_tokens=4096, verbose=False  # type: ignore
    )
    output = str(result)
    print(output)
except Exception as e:
    print(f"Error during generation: {e}")
    # Fallback to stream_generate with proper handling
    try:
        for token in stream_generate(
            model, processor, formatted_prompt, pil_image, max_tokens=4096, verbose=False  # type: ignore
        ):
            token_str = str(token)
            output += token_str
            print(token_str, end="")
            if "</doctag>" in token_str:
                break
    except Exception as stream_error:
        print(f"Error during streaming generation: {stream_error}")
        output = "<doctag>Error generating output</doctag>"

print("\n\n")

# Populate document
try:
    doctags_doc = DocTagsDocument.from_doctags_and_image_pairs([output], [pil_image])
    # create a docling document
    doc = DoclingDocument.load_from_doctags(doctags_doc, document_name="SampleDocument")

    ## Export as any format
    # Markdown
    print("Markdown: \n\n")
    markdown_output = doc.export_to_markdown()
    print(markdown_output)

    # HTML
    if SHOW_IN_BROWSER:
        import webbrowser

        out_path = Path(OUTPUT_HTML_PATH)
        doc.save_as_html(out_path, image_mode=ImageRefMode.EMBEDDED)
        webbrowser.open(f"file:///{str(out_path.resolve())}")

    # Comparison output
    if COMPARE_WITH_TEXTRACT and textract_output:
        comparison_text = format_comparison(markdown_output, textract_output)
        
        print("\n" + "="*80)
        print("                         DOCLING vs TEXTRACT COMPARISON")
        print("="*80)
        print(comparison_text)
        
        # Save comparison to file
        comparison_path = Path(COMPARISON_OUTPUT_PATH)
        with open(comparison_path, 'w', encoding='utf-8') as f:
            f.write(comparison_text)
        print(f"Detailed comparison saved to: {comparison_path.resolve()}")
    elif COMPARE_WITH_TEXTRACT:
        print("\nTextract comparison was enabled but failed. Check AWS credentials.")

except Exception as e:
    print(f"Error processing document: {e}")
    print("Make sure the model output contains valid DocTags format.")
