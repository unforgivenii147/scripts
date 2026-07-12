#!/data/data/com.termux/files/usr/bin/env python
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

def chunk_file(file_path, chunk_size=5000):
    chunks = []
    current_chunk = ""
    start_line = 0
    current_line = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            if len(current_chunk) + len(line) > chunk_size and current_chunk:
                chunks.append((start_line, current_line - 1, current_chunk))
                current_chunk = line
                start_line = current_line
            else:
                current_chunk += line
            current_line += 1
        
        if current_chunk:
            chunks.append((start_line, current_line - 1, current_chunk))
    
    return chunks

def translate_chunk(chunk_data):
    from deep_translator import GoogleTranslator
    
    start_line, end_line, text = chunk_data
    
    try:
        translator = GoogleTranslator(source_language='fa', target_language='en')
        translated = translator.translate(text)
        
        return {
            "chunk_id": f"{start_line}_{end_line}",
            "start_line": start_line,
            "end_line": end_line,
            "original": text,
            "translated": translated
        }
    except Exception as e:
        print(f"Error translating chunk {start_line}_{end_line}: {e}")
        return None

def main():
    input_file = Path("words.txt")
    
    if not input_file.exists():
        print(f"Error: {input_file} not found")
        return
    
    print("Extracting chunks...")
    chunks = chunk_file(input_file)
    print(f"Total chunks: {len(chunks)}")
    
    print("Translating chunks in parallel...")
    translations = []
    
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(translate_chunk, chunk) for chunk in chunks]
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            if result:
                translations.append(result)
            completed += 1
            print(f"Progress: {completed}/{len(chunks)}")
    
    print("Writing results...")
    with open("fa_en.json", 'w', encoding='utf-8') as f:
        json.dump({"translations": sorted(translations, key=lambda x: x["start_line"])}, f, ensure_ascii=False, indent=2)
    
    print("Done! Output: fa_en.json")

if __name__ == "__main__":
    main()
