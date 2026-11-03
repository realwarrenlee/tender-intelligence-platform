import unicodedata


def normalise_quote(text):
    return ' '.join(unicodedata.normalize('NFKC',text).split())


def citation_errors(citations,anchors,roles=None):
    errors=[]
    for cite in citations:
        anchor=anchors.get(cite['anchor_id'])
        quote=normalise_quote(cite['quote'])
        if not quote:
            errors.append('Citation quote is empty after normalisation.')
        elif anchor is None:
            errors.append('Citation anchor is outside the pinned source manifest.')
        elif quote not in normalise_quote(anchor['text']):
            errors.append(f'Citation quote does not occur in pinned anchor {cite["anchor_id"]}: {cite["quote"][:200]!r}. Use exact contiguous spans; do not join text across table columns.')
        elif roles and anchor['source_role'] not in roles:
            errors.append('Citation uses an unauthorised source role.')
        if anchor:
            locations=[anchor.get('page'),anchor.get('paragraph'),anchor.get('answer_id')]
            if sum(value is not None for value in locations)!=1:
                errors.append('Anchor must have exactly one source location.')
            if any(value is not None and (not isinstance(value,int) or isinstance(value,bool) or value<1) for value in locations[:2]):
                errors.append('PDF/DOCX locations must be positive one-based integers.')
            if anchor['source_role']=='review_answer' and not anchor.get('answer_id'):
                errors.append('Review evidence requires an attributed answer location.')
    return errors
