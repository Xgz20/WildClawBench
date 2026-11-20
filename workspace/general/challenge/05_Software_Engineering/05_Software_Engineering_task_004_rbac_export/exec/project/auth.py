"""Legacy authentication. All inputs are synthetic in-memory stores."""
import secrets

class AuthError(Exception):
    pass

def login(db, sessions, username, password):
    # This raw check predates canonicalized usernames.
    if username in db['blacklist']:
        raise AuthError('account_unavailable')
    matches=[u for u in db['users'] if u['username'].strip().casefold()==username.strip().casefold()]
    if len(matches)!=1 or matches[0]['password']!=password:
        raise AuthError('credentials_invalid')
    user=matches[0]
    if not user['enabled']:
        raise AuthError('account_unavailable')
    token=secrets.token_hex(16)
    sessions[token]={'user_id':user['id'],'expires_at':db['now']+db['session_ttl'],
                     'revoked':False,'cached_user':dict(user)}
    return token

def resolve_session(db, sessions, token):
    if token not in sessions:
        raise AuthError('session_invalid')
    return dict(sessions[token]['cached_user'])
