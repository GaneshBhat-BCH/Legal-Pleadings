import re

def chunk_text(text: str, target_chunk_size: int = 1000, min_chunk_size: int = 100) -> list[str]:
    """
    Chunks text using a Variable Chunking strategy.
    
    Strategy:
    1. Split text into sentences using regex.
    2. Aggregate sentences into chunks.
    3. Finalize a chunk when it reaches 'target_chunk_size'.
    4. Ensures chunks break at sentence boundaries for semantic integrity.
    
    Args:
        text (str): Input text.
        target_chunk_size (int): Soft limit for chunk character count.
        min_chunk_size (int): Minimum size to avoid tiny trailing chunks (soft enforcement).
    
    Returns:
        list[str]: List of text chunks.
    """
    if not text:
        return []

    # Regex to split by punctuation followed by whitespace, keeping the punctuation
    # (?<=[.!?]) lookbehind asserts we split AFTER one of these chars
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sent_len = len(sentence)
        
        # If this single sentence is huge (larger than target), we might have to split it blindly
        # or just accept it as a large chunk. For this logic, we'll accept it to preserve meaning
        # unless it's excessively huge, but let's keep it simple: just append if empty, else split.
        
        if current_length + sent_len > target_chunk_size and current_length > 0:
            # Finalize current chunk
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0
            
        current_chunk.append(sentence)
        current_length += sent_len
        
    # Append the last chunk if exists
    if current_chunk:
        chunks.append(" ".join(current_chunk))
            
    return chunks
