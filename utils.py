# utils.py

def clean_text(text, max_length):
    """Cleans raw HTML/text and truncates it to a maximum length."""
    if not isinstance(text, str):
        return ""
        
    # Strip leading/trailing whitespace
    cleaned = text.strip()
    
    # Enforce the max length limit
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "..."
        
    return cleaned