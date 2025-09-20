#!/usr/bin/env python3
"""
Simple PDF compression test using Ghostscript directly.
This tests if the core PDF processing functionality works.
"""

import os
import tempfile
import subprocess


def create_sample_pdf():
    """Create a simple PDF file for testing."""
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
>>
endobj

4 0 obj
<<
/Length 150
>>
stream
BT
/F1 12 Tf
72 720 Td
(Hello World - This is a test PDF file for compression testing.) Tj
0 -20 Td
(This file contains some text to make it compressible.) Tj
0 -20 Td
(More text content to increase file size for testing.) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000284 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
483
%%EOF"""
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    with os.fdopen(fd, 'wb') as f:
        f.write(pdf_content)
    
    return temp_path


def test_ghostscript_compression():
    """Test PDF compression using Ghostscript directly."""
    print("Direct Ghostscript PDF Compression Test")
    print("=" * 45)
    
    try:
        # Create a sample PDF
        input_pdf = create_sample_pdf()
        print(f"✓ Created sample PDF: {input_pdf}")
        
        original_size = os.path.getsize(input_pdf)
        print(f"✓ Original PDF size: {original_size} bytes")
        
        # Create output file
        output_pdf = tempfile.mktemp(suffix='_compressed.pdf')
        
        # Build Ghostscript command for medium quality compression
        gs_command = [
            '/usr/bin/gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/ebook',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            '-sOutputFile=' + output_pdf,
            input_pdf
        ]
        
        print("✓ Running Ghostscript compression...")
        print(f"Command: {' '.join(gs_command)}")
        
        # Execute Ghostscript
        result = subprocess.run(
            gs_command,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✓ Ghostscript execution successful")
            
            if os.path.exists(output_pdf):
                compressed_size = os.path.getsize(output_pdf)
                compression_ratio = compressed_size / original_size
                savings = (1 - compression_ratio) * 100
                
                print(f"✓ Compressed PDF created: {output_pdf}")
                print(f"✓ Compressed size: {compressed_size} bytes")
                print(f"✓ Compression ratio: {compression_ratio:.2f}")
                print(f"✓ Size reduction: {savings:.1f}%")
                
                # Validate the compressed PDF
                validate_command = ['/usr/bin/gs', '-dNODISPLAY', '-dQUIET', '-dBATCH', output_pdf]
                validate_result = subprocess.run(validate_command, capture_output=True)
                
                if validate_result.returncode == 0:
                    print("✓ Compressed PDF is valid")
                    return True
                else:
                    print(f"❌ Compressed PDF validation failed: {validate_result.stderr}")
                    return False
            else:
                print("❌ Compressed PDF file was not created")
                return False
        else:
            print(f"❌ Ghostscript failed with return code {result.returncode}")
            print(f"Error output: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Ghostscript execution timed out")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if 'input_pdf' in locals() and os.path.exists(input_pdf):
            os.unlink(input_pdf)
        if 'output_pdf' in locals() and os.path.exists(output_pdf):
            os.unlink(output_pdf)
    
    return False


if __name__ == '__main__':
    if test_ghostscript_compression():
        print("\n🎉 PDF compression test PASSED!")
        print("✅ Core PDF processing functionality is working correctly!")
        exit(0)
    else:
        print("\n❌ PDF compression test FAILED!")
        exit(1)
