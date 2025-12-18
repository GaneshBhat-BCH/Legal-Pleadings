def chunk_text(text: str, chunk_size: int = 2000, overlap_percent: int = 20) -> list[str]:
    """
    Chunks text into specific size with overlapPercentage.
    Chunk size: 2000 characters (~500 tokens)
    Overlap: 20% (400 characters)
    """
    if not text:
        return []

    overlap_size = int(chunk_size * (overlap_percent / 100))
    stride = chunk_size - overlap_size

    chunks = []
    
    # Simple sliding window approach
    for i in range(0, len(text), stride):
        # Slice from i to i + chunk_size
        chunk = text[i:i + chunk_size]
        if chunk.strip(): # Avoid empty chunks
            chunks.append(chunk)
            
    return chunks
