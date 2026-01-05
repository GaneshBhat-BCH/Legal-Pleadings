import re
import os
import subprocess
import sys

# Configuration
MD_FILE = r"c:\Users\GaneshBhat\OneDrive - Novatio Solutions\Desktop\Test\TECHNICAL_ARCHITECTURE.md"
OUTPUT_DIR = r"c:\Users\GaneshBhat\OneDrive - Novatio Solutions\Desktop\Test\diagrams"

def extract_mermaid_blocks(md_content):
    blocks = []
    # Regex to find mermaid blocks and try to capture preceding context for naming
    # We'll split by lines and iterate to keep track of headers
    lines = md_content.splitlines()
    custom_name = "diagram"
    
    current_block = []
    in_block = False
    
    for line in lines:
        stripped = line.strip()
        
        # Track headers for naming
        if stripped.startswith("#"):
             # Clean header to be filename friendly
             clean_header = re.sub(r'[^\w\s-]', '', stripped).strip().replace(' ', '_').lower()
             # remove leading #s
             clean_header = re.sub(r'^_+', '', clean_header)
             custom_name = clean_header
        
        if stripped.startswith("```mermaid"):
            in_block = True
            current_block = []
            continue
            
        if stripped.startswith("```") and in_block:
            in_block = False
            if current_block:
                blocks.append({
                    "name": custom_name,
                    "code": "\n".join(current_block)
                })
                # increment generic counter just in case multiple diagrams under one header
                custom_name = f"{custom_name}_next"
            continue
            
        if in_block:
            current_block.append(line)
            
    return blocks

def main():
    if not os.path.exists(OUTPUT_DIR):
        print(f"Creating directory: {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR)
        
    print(f"Reading {MD_FILE}...")
    try:
        with open(MD_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    blocks = extract_mermaid_blocks(content)
    print(f"Found {len(blocks)} mermaid diagrams.")
    
    if not blocks:
        print("No diagrams found.")
        return

    # Check if npx is available
    try:
        subprocess.run(["npx", "--version"], shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        print("Error: 'npx' is not available in the path. Please install Node.js.")
        return

    for i, block in enumerate(blocks):
        safe_name = block['name']
        # If name became too long or duplicate, maybe append index
        filename = f"{i+1:02d}_{safe_name}.png"
        mmd_filename = f"temp_{i}.mmd"
        
        out_path = os.path.join(OUTPUT_DIR, filename)
        mmd_path = os.path.join(OUTPUT_DIR, mmd_filename)
        
        print(f"Generating {filename}...")
        
        with open(mmd_path, 'w', encoding='utf-8') as f:
            f.write(block['code'])
            
        # Run mermaid-cli
        # Background color white for better visibility (-b transparent is default usually)
        # -t dark or default
        cmd = f'npx -y @mermaid-js/mermaid-cli -i "{mmd_path}" -o "{out_path}" -b white -s 3'
        
        try:
            subprocess.run(cmd, shell=True, check=True)
            print(f"Success: {out_path}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to render {filename}: {e}")
        finally:
            if os.path.exists(mmd_path):
                os.remove(mmd_path)

if __name__ == "__main__":
    main()
