"""
Scénář promo videa (≤ 3 min, česky, technické publikum) – jediný zdroj pravdy pro record.py (co natočit) i render.py (co namluvit).

Scéna = karta (titulní obrazovka s komponentami vrstvy, renderuje Playwright z HTML) nebo gui (klip z nahrávky řídicího pultu).
Délku scény určuje komentář (TTS): karta drží obraz po celou dobu, klip GUI se zkrátí nebo podrží poslední snímek.
Komentář ~430 slov ≈ 2:50 při rate +4 % (cs-CZ neurální hlas). Text čte TTS doslova – čísla a zkratky psát tak, jak se mají vyslovit.
"""

VOICE = "cs-CZ-AntoninNeural"   # alternativa cs-CZ-VlastaNeural
RATE = "+4%"

SCENES = [
    {"id": "01-intro", "kind": "card", "layer": None, "title": "Autonomní IT firma na jedné platformě",
     "sub": "zakázka od poptávky po merge – role agentů, člověk jen u nevratných kroků",
     "bullets": ["Azure Kubernetes Service · GitOps (Flux) · vše měřené harnessem", "8 rozhodnutých vrstev architektury", "open source stack + Claude přes Anthropic API"],
     "say": "Tohle je autonomní firma. Zakázku od poptávky až po merge do repozitáře odbaví role agentů a člověk rozhoduje jen tam, kde je krok nevratný. "
            "Celé to běží na Azure Kubernetes Service, konfigurace žije v Gitu a nasazuje ji Flux."},
    {"id": "02-pult", "kind": "gui", "title": "Řídicí pult firmy – AG-UI klient",
     "say": "Řídicí pult firmy je vlastní klient protokolu AG-UI. Každá zakázka je thread, běh rolí je stream událostí a rozhodnutí člověka je interrupt s povinným důvodem."},
    {"id": "03-zalozeni", "kind": "gui", "title": "Založení zakázky – klasifikační brána a rozpočet",
     "say": "Zakládáme zakázku. Klasifikační brána podle AI Actu určí profil rizika dřív, než se spustí první agent. Rozpočet v dolarech je tvrdý strop – hlídá ho gateway, ne prompt."},
    {"id": "04-orchestrace", "kind": "card", "layer": "2", "title": "Agentní smyčka a orchestrace",
     "sub": "Claude Agent SDK · Dapr Workflows · PostgreSQL state store",
     "bullets": ["procesy P1–P5 jako durable workflow, replay z historie", "named versioning – instance nese verzi orchestrátoru", "role = YAML: SVID, OPA data, rozpočet, scope paměti, sandbox profil"],
     "say": "Procesy firmy jsou Dapr Workflows: durable, přehrávané z historie a verzované. Každá role běží jako Claude Agent SDK v izolovaném podu a výsledek vrací orchestrátoru."},
    {"id": "05-role", "kind": "gui", "title": "Role Account běží – Kata pod, sandbox-runtime",
     "say": "Role Account právě běží jako Kata pod, tedy virtuální stroj na úrovni podu. Uvnitř drží sandbox-runtime jediný egress přes gateway. "
            "V pultu vidíme subagenty, náklady a tahy v reálném čase."},
    {"id": "06-gateway", "kind": "card", "layer": "3", "title": "Model gateway a FinOps",
     "sub": "agentgateway · /v1/messages · klíč per role × zakázka · rozpočty v USD",
     "bullets": ["modely, git i GitHub jen přes gateway (CONNECT allow-list, backendAuth)", "tajemství: Key Vault → External Secrets → gateway; aplikace ani pod je nevidí", "per-request ledger → OpenTelemetry → ClickHouse; neznámý alias = 404"],
     "say": "Všechny modely, git i GitHub jdou přes agentgateway. Každá role má na každou zakázku vlastní klíč s rozpočtem. "
            "Tajemství zná jen gateway – dostává je z Key Vaultu přes External Secrets. Neznámý model končí chybou čtyři sta čtyři, žádný tichý fallback."},
    {"id": "07-h1", "kind": "gui", "title": "H1 – přijetí zadání člověkem (důvod, podepsaný token, mandát)",
     "say": "Přijetí zadání je rozhodnutí člověka. Důvod je povinný, token schválení je podepsaný a vázaný na hash artefaktu – executor nevratné akce nic jiného nepřijme. "
            "Schvalovatel se zároveň stává mandátem, jehož jménem další role jednají."},
    {"id": "08-identita", "kind": "card", "layer": "4", "title": "Identita, autorizace, governance",
     "sub": "Keycloak · SPIRE · OPA · OpenBao",
     "bullets": ["člověk: OAuth z Keycloaku, token exchange – sub schvalovatele, azp klienta role", "agent: SPIFFE SVID per pod jako druhý credential", "jedna Rego pro gateway, paměť i executor; tajemství v OpenBao a Key Vaultu"],
     "say": "Identita člověka přichází z Keycloaku, identita agenta je SPIFFE SVID per pod. Jedna politika v OPA rozhoduje pro gateway, pro nástroje paměti i pro executor. "
            "Tajemství drží OpenBao a Key Vault."},
    {"id": "09-navrh-pr", "kind": "gui", "title": "Architekt → vývojář v sandboxu → pull request → H4 merge",
     "say": "Architekt navrhne řešení, vývojář ho implementuje v sandboxu a výsledkem je pull request. Merge je opět rozhodnutí člověka – bod H4."},
    {"id": "10-firma", "kind": "gui", "title": "Firma – verze orchestrátoru, stop tenanta, autonomie rolí",
     "say": "Pohled na firmu: verze orchestrátoru a instance per verze, stop tenanta jedním rozhodnutím – klíče dostanou limit nula a pody skončí do minuty – a posun autonomie role jen při splněných metrikách."},
    {"id": "11-finops", "kind": "gui", "title": "FinOps – rozpočty v gateway × per-request ledger v ClickHouse",
     "say": "FinOps ze dvou nezávislých zdrojů: rozpočty klíčů v gateway a per-request ledger v ClickHouse přes OpenTelemetry Collector. Rozdíl mezi nimi je sám o sobě kontrola."},
    {"id": "12-governance", "kind": "gui", "title": "Governance a audit – risk register, SLA, export pro deployera",
     "say": "Governance report, risk register a audit všech lidských rozhodnutí. Export pro deployera podle článku třináct AI Actu obsahuje jen řádky vlastního tenanta – díky row-level security v Postgresu."},
    {"id": "13-outro", "kind": "card", "layer": None, "title": "Měřeno, ne slibováno",
     "sub": "82 automatických kontrol proti AKS po každé změně · P0–P4 hotovo · další krok: ostrý běh",
     "bullets": ["Dapr · agentgateway · Keycloak · SPIRE · OPA · OpenBao · ClickHouse · Kata – Apache-2.0", "Claude Agent SDK, MCP, AG-UI, A2A za adaptérem", "github.com/akczcz/adam"],
     "say": "Všechno, co jste viděli, je měřené: přes osmdesát automatických kontrol běží proti clusteru po každé změně. "
            "Stack je open source – Dapr, agentgateway, Keycloak, SPIRE, OPA, OpenBao, ClickHouse, Kata – a modely Claude přes Anthropic API. Příští krok: první ostrý běh s živým modelem."},
]


def by_id(sid): return next(s for s in SCENES if s["id"] == sid)
