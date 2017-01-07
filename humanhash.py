import zipfile

_words = {}
def words():
    global _words
    if _words == {}:
        with zipfile.ZipFile('wordlists.zip') as zf:
            for category in ['adjectives', 'nouns']:
                for l in [1, 2]:
                    name = '{}/{}syllable{}.txt'.format(category, l, category)
                    _words.setdefault(category, []).extend(zf.read(name).splitlines())
    
    return _words
                      
def humanhash(o):
    if isinstance(o, int):
        o = str(o)
        
    code = str(hash(o))
    adjective = words()['adjectives'][int(code[10:]) % len(words()['adjectives'])]
    noun = words()['nouns'][int(code[:10]) % len(words()['nouns'])]
    
    return adjective.lower() + b'-' + noun.lower() 