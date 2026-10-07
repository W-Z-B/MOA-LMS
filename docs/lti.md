# Outside tools (LTI 1.3 with Advantage)

Checklist item 6.07. The GSA LMS is an LTI 1.3 **platform**: outside tools (a simulation, a publisher's
question bank, a video service) open from a course without a second sign-in, can be filled with content
chosen inside the tool, post scores to the gradebook, and can read the class list. Code: `api/lti/`.
The privacy position is in the impact assessment, section 7a (`docs/privacy/dpia.md`).

## Adding a tool

A course administrator registers each tool once, in **Admin, Outside tools** (`#/admin/tools`).

1. Give the tool's maker the LMS's details, shown on that screen (also `GET /api/v1/lti/platform/`):

   | The maker asks for | Give them |
   |---|---|
   | Issuer (platform ID) | `LTI_ISSUER`, by default the LMS's public address |
   | Client ID | Shown once the tool is registered (the LMS makes it) |
   | Deployment ID | `1` unless you change it |
   | Public keyset URL (JWKS) | `<public address>/api/lti/jwks/` |
   | OIDC authorisation URL | `<public address>/api/lti/auth/` |
   | OAuth2 access token URL | `<public address>/api/lti/token/` (audience: the same address) |
   | Deep linking return URL | `<public address>/api/lti/deep-links/` (sent in each request anyway) |

2. Register the tool with the details the maker gives you: its **login initiation address** (OIDC login),
   its **launch address** (target link), its **content selection address** if it offers one (deep
   linking), any further addresses launches may be sent to, and its key: its **key set address** (JWKS
   URL) or its **public key** pasted in (PEM or one JWK). Every address must start `https://`.
3. Decide what the tool may do: post scores to the gradebook (on by default), read class lists (off).
4. Decide what it may know about people. **Names** and **email addresses** are each **off by default**.
   Switch one on only when the tool cannot work without it and GSA has recorded why (DPIA section 7a).
5. Switching a tool off stops every launch and every service call at once. A tool still placed on a
   course cannot be removed; switch it off instead.

## What each tool receives

| When | Always | Only if switched on for the tool |
|---|---|---|
| A launch (id_token, signed RS256 by the LMS) | An identifier for the person, random and different for each tool; their role on the course (Learner, Instructor, Instructor#TeachingAssistant or Administrator); the course's code and title (context); the item's title and resource link id; the deployment id; custom values the tool asked for | Name (`name`, `given_name`, `family_name`); email (`email`) |
| A class list (NRPS 2.0) | The same identifier and role for every active member | Names and emails, as above |
| Grade services (AGS 2.0) | The tool's own line items and the results it posted | |

Nothing else is ever sent: no student or employee number, no username, no marks from elsewhere.

## Placing a tool on a course

Teaching staff open the course's **Tools** tab:

- **Add a tool** places it in a module as a link item (a draft until published). Give a maximum score to
  make a gradebook column the tool can post to.
- **Choose content in the tool** opens the tool's content selection (Deep Linking 2.0) in a new window;
  each item chosen comes back as a draft link in the module, with a gradebook column if the tool asks
  for one.
- Each **gradebook column** shows in the gradebook. Give it a weight (and a category if the course uses
  them) and it counts in the coursework total; at weight 0 it is shown but does not count.

## The flow and the checks

| Step | Address | Refused when |
|---|---|---|
| A person opens a placement | `GET /api/lti/launch/<item>/` (signed in) | The tool is off; the person is not on the course; a student opens a draft |
| Teaching staff choose content | `GET /api/lti/choose/?tool=&module=` | Not teaching on the course; the tool has no content selection |
| The tool's authentication request | `GET or POST /api/lti/auth/` | Unknown client id; the answer address was not registered; the login hint was not issued by the LMS, was used before, is older than `LTI_LAUNCH_SECONDS` (300), or belongs to someone else signed in; no nonce, or a nonce the tool used before |
| The content chosen comes back | `POST /api/lti/deep-links/` (field `JWT`) | Not signed by the tool's key; not addressed to the LMS; expired; wrong deployment id; no nonce or a used one; not the answer to a selection the LMS began, or already answered, or later than `LTI_DEEP_LINK_SECONDS` (3600); an item address that is not https |
| The tool asks for a token | `POST /api/lti/token/` | Not a client credentials grant with a signed client assertion; assertion not signed by the tool's key, expired, wrong audience, no `jti` or a `jti` used before; no scope the tool is allowed |
| Line items, scores, results | `/api/lti/sites/<site>/line-items/...` | No valid bearer token or scope; the tool is not placed on that course; the line item is another tool's; a score for someone who is not a student of the course; a score older than the one held (409) |
| The class list | `GET /api/lti/sites/<site>/members/` | As above, and the tool is not allowed class lists |

The LMS's key pair is made the first time it is needed and kept encrypted with the application key; to
change it, make a new key (`lti.keys.make_key()`): the old one stays in the key set so tokens already issued
still check. A tool's key set is cached for `LTI_JWKS_CACHE_SECONDS` (3600). Clock difference allowed:
`LTI_CLOCK_LEEWAY_SECONDS` (60). Tokens for the services last `LTI_TOKEN_SECONDS` (3600).

Launches open the tool in a new window (`document_target: window`): the LMS's pages refuse to be framed.

## Audit

Every registration and change of a tool, every placement and gradebook column, every launch (with whether
names or emails were sent), every class-list reading and every score posted is in the audit log.
