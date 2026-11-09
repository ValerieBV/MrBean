"""Compare ASR text to the literal video script; this is not a pronunciation score."""
import re
import unicodedata

MAX_REFERENCE_WORDS = 1500
MAX_TRANSCRIPT_WORDS = 3000


def words(text):
    text = unicodedata.normalize('NFKC', text).casefold().replace('’', "'")
    # Expand common unambiguous forms; names, numbers and ASR ambiguity remain reviewable.
    text = re.sub(r"\bwon't\b", 'will not', text)
    text = re.sub(r"\bcan't\b|\bcannot\b", 'can not', text)
    text = re.sub(r"\b(\w+)n't\b", r'\1 not', text)
    for ending, expanded in [("'m",' am'),("'re",' are'),("'ve",' have'),("'ll",' will')]:
        text = re.sub(re.escape(ending)+r'\b', expanded, text)
    return re.findall(r"[^\W_]+(?:'[^\W_]+)?", text)


def compare_reading(reference, transcript):
    if not isinstance(reference, str) or not isinstance(transcript, str):
        raise ValueError('invalid_reading_text')
    ref, heard = words(reference), words(transcript)
    n, m = len(ref), len(heard)
    if not n or n > MAX_REFERENCE_WORDS or not m or m > MAX_TRANSCRIPT_WORDS:
        raise ValueError('reading_text_missing_or_too_long')
    # Exact edit-distance alignment with compact backtrace (not a bag-of-words count).
    directions = [bytearray(m+1) for _ in range(n+1)]
    directions[0][1:] = bytes([2])*m
    previous = list(range(m+1))
    for i in range(1,n+1):
        row = [i]+[0]*m
        directions[i][0] = 1
        for j in range(1,m+1):
            diagonal = previous[j-1]+int(ref[i-1]!=heard[j-1])
            delete, insert = previous[j]+1, row[j-1]+1
            best = min(diagonal,delete,insert)
            row[j] = best
            directions[i][j] = 0 if diagonal==best else (1 if delete==best else 2)
        previous = row
    ops=[];i,j=n,m
    while i or j:
        direction=directions[i][j]
        if direction==0:
            i-=1;j-=1
            ops.append(('match' if ref[i]==heard[j] else 'substitution',ref[i],heard[j]))
        elif direction==1:
            i-=1;ops.append(('missing',ref[i],''))
        else:
            j-=1;ops.append(('extra','',heard[j]))
    ops.reverse()
    counts={kind:sum(op[0]==kind for op in ops) for kind in ['match','substitution','missing','extra']}
    errors=counts['substitution']+counts['missing']+counts['extra']
    return {'reference_words':n,'transcript_words':m,'matched_words':counts['match'],
            'missing_words':counts['missing'],'different_words':counts['substitution'],
            'extra_words':counts['extra'],'coverage_percent':round(counts['match']/n*100,2),
            'differences':[{'type':kind,'reference':r,'transcript':t} for kind,r,t in ops if kind!='match'][:100],
            'difference_count':errors}
