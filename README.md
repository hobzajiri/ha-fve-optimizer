# FVE Optimizer

Vlastní integrace pro Home Assistant, která rozděluje přebytky z fotovoltaiky mezi
domácí baterii, bojler, nabíjení auta a další zařízení podle priorit.

Je stavěná na instalaci s omezovaným přetokem (Growatt SPH): když spotřebiče můžou
brát přebytky, integrace zvedne limit přetoku, takže skrytý přebytek je vidět
na elektroměru a není potřeba ho odhadovat zkoušením.

## Jak to funguje

Každých N sekund (výchozí 15 s) dispečer:

1. Přečte výkon sítě, baterie a SoC.
2. Určí, jestli má přednost baterie. Ta má přednost do **cílového SoC**. Pokud
   zbývající predikce (Solcast) pokryje dobití baterie i spotřebu domu do západu
   slunce (× bezpečnostní koeficient), cíl se sníží na **SoC při dostatečné
   predikci** a spotřebiče dostanou přebytky dřív.
3. Spočítá **přebytek k rozdělení**:
   `spotřeba řízených zařízení − výkon sítě (+ nabíjení baterie, pokud už nemá přednost) − rezerva`
4. Rozdělí ho mezi zařízení podle priority (nižší číslo = dřív).
5. Řídí limit přetoku s co nejméně zápisy do střídače:
   * **zvedne ho jednou denně ráno**, když je kam ukládat (bojler, auto) a
     predikce slibuje přebytek nad spotřebu domu a dobití baterie,
   * **sníží ho jen tehdy, když není kam ukládat** (plná baterie, nahřátý
     bojler, nabité nebo odpojené auto); večer bez výroby se nemění,
   * znovu ve stejný den jen s **Povolit přetok znovu během dne**,
   * po restartu převezme aktuální limit, nic nepřepisuje.
6. Pokud jsou zadané proudy fází, hlídá hlavní jistič.

## Typy zařízení

Zařízení se přidávají v **Nastavení → Zařízení a služby → FVE Optimizer →
Přidat …** a každé se dá později upravit. Další typy stačí doplnit jako podtřídu
`ManagedDevice` v `devices.py` a flow v `config_flow.py`.

| Typ | Použití | Řízení |
| --- | --- | --- |
| Spínané zařízení | bojler, přímotop, čerpadlo | zap/vyp při dostatečném přebytku, hlídá teplotu, min. doba zapnutí/vypnutí |
| Nabíječka EV | EcoVolter (`rattkin/ha-ecovolter-integration`) | proud 6–16 A, přepínání 1/3 fází s omezením četnosti |

### Baterie: cíl podle doby bez výroby

S přepínačem **Cíl podle doby bez výroby** má baterie přednost jen do SoC,
které pokryje spotřebu od západu do východu slunce:

`cíl = rezerva + příkon bez výroby × (noc + doba navíc) / kapacita`

Příklad: noc 12,2 h + 2 h navíc, 400 W, 10 kWh, rezerva 10 % → **66,8 %**.
**Maximální cílové SoC** je strop. Když predikce ukáže, že do západu slunce
bude výroby dost, cíl se ještě sníží na **Cílové SoC při dostatečné predikci**.
Když výroba nestačí, baterie se večer stejně vybije. Bojler a auto proto smí
v HDO brát i z baterie.

### Auto: maximální SoC a ráno alespoň X %

S **SoC auta** (např. z integrace MySkoda) má nabíječka dvě nezávislá SoC,
stejně jako bojler dvě teploty:

* **Maximální SoC z přebytků**: do něj se auto nabíjí z přebytků. Buď
  **entita limitu nabití z auta** (např. MySkoda), nebo pevné číslo
  (záloha, když entita ještě nikdy nebyla dostupná). Krátký výpadek entity
  drží poslední známý limit (neskočí na 100 %). Po dosažení maxima se znovu
  zapne až po poklesu o **dolní hysterezi** – nahoru se cíl nezvyšuje
  (auto by vyšší limit stejně nepřijalo); když se limit **zvedne**, hystereze
  se uvolní. Ranní termín smí jet i nad surplus maximum až do minimálního SoC.
* **Minimální SoC v termínu** (např. 60 % do 07:00): garantované minimum, viz níže.

**Objednávka nabití**: na kartě u nabíječky (Cíl % + termín → Objednat), nebo
služba `fve_optimizer.set_ev_charge_order`. Respektuje HDO. **Do 80 %** se
dobíjí dřív (přebytek / NT okna); **80–100 %** až těsně před termínem.
Zrušení na kartě nebo `clear_ev_charge_order`.

**Rychlé nabíjení**: tlačítko na kartě / `start_ev_boost` — od teď naplno
(bez HDO), s odhadem času. Stop na kartě nebo `stop_ev_boost`.

S **Nabít do termínu** přibude **Termín nabití**, **Minimální SoC v termínu**,
**Kapacita baterie auta**, **Účinnost nabíjení** a **Dobíjet do termínu jen v HDO**.

* Přes den se nabíjí z přebytků do maximálního SoC.
* Když přebytky nestačí, dobije se na plný proud:
  * **jen v HDO**: v nejpozdějších oknech HDO před termínem, která stačí,
  * **kdykoli**: těsně před termínem.
* Po termínu se cíl posune na další den.

### Ochrana proti legionele

**Ochrana proti legionele** jednou za **interval** (7 dní) ohřeje vodu na
**teplotu proti legionele** (65 °C). Maximální teplota z přebytků se dočasně
zvýší, takže se to obvykle stihne z přebytků. S **Nahřát do termínu** se
v termínu dohřeje i ze sítě (v HDO). Datum posledního ohřevu přežije restart
(atribut `legionella_last`). Termostat bojleru musí tuto teplotu dovolit.

### Poslední rozhodnutí

`sensor.fve_optimizer_last_decision` (česky „Poslední rozhodnutí“) má čitelný
souhrn, např. *Baterie 72 % → cíl 67 % (přednost zařízení) · Bojler: běží
2000 W · EcoVolter: nabíjí 2990 W (1f 13 A)*. Mění se jen při změně
rozhodnutí, takže v logbooku je historie, proč se co stalo. Podrobnosti jsou
v atributu `details`.

### Pořadí: minimum před baterií

1. **Nucený režim** (termín bojleru, legionela, auto ráno) – běží vždy.
2. **Zařízení pod minimem** (bojler pod teplotou v termínu, auto pod minimálním
   SoC) dostanou přebytek **před baterií**, ale jen do minima. Jinak by se
   baterie nabila ze slunce a večer vybila do bojleru – zbytečný cyklus se
   ztrátami. Vypíná se přepínačem **Minimum před baterií**.
3. **Baterie** do cílového SoC – dokud má přednost, zařízení dostanou jen
   přebytek nad **Max. nabíjecí výkon baterie** a i běžící zařízení uhnou.
4. **Ostatní** podle priority (ohřev nad minimum, nabíjení nad minimum…).

### Dorovnání z plné baterie

Zařízení nastavují výkon po krocích (auto po 1 A = 690 W na 3 fázích, bojler
jen celým příkonem). Když je baterie plná, zaokrouhlí se na **nejbližší** krok
a rozdíl, nejvýš polovinu kroku, dorovná baterie. Přebytek tak neteče do sítě.

* Začne při **SoC plné baterie** (99 %), skončí o 5 % níž (94 %). Pak se baterie
  dobije a začne to znovu – mělké cykly nahoře baterii nevadí.
* Jen při výrobě a když baterie nemá přednost.
* Zapínání a vypínání dál hlídají zpoždění a minimální doby běhu.
* Vypíná se přepínačem **Dorovnávat z plné baterie**.

### Karta FVE Optimizer

Integrace přináší vlastní kartu (bez HACS) s rozhodnutím: souhrn (režim, priorita,
přebytek, predikce, tarif, limit přetoku, jistič), řízená zařízení s doporučením
(v režimu Jen sledovat s tlačítkem Provést) a log. Na toky energie použij např. Power Flow Card
Plus; vlastní schéma toků jde zapnout částí `flow`. Obnovuje se každý cyklus.
Pomocí `sections` jde kartu rozdělit do více sloupců, např. jedna karta
s doporučeními a druhá jen s logem
(`sections: [log]`). Log ukazuje jen to, co se oproti předchozímu rozhodnutí
změnilo; celé rozhodnutí je v nápovědě po najetí myší.

```yaml
type: custom:fve-optimizer-card
entity: sensor.fve_optimizer_status   # entita „Stav“ FVE Optimizeru
title: FVE Optimizer                  # volitelné, false = bez nadpisu
log: 20                               # počet řádků logu rozhodnutí, false = bez logu
sections: [summary, devices, log]   # výchozí; + flow = schéma toků
```

### Bezpečnost

* **Pojistka při výpadku dat:** když síť, baterie nebo SoC ze střídače
  nedostupné déle než **Časový limit dat** (5 min), nebo se *všechny*
  kritické vstupy déle nehlásí (zamrzlé), zařízení řízená přebytky se vypnou
  přes svá zpoždění a minimální doby. Krátký výpadek nebo zápis jen při změně
  stavu (typické u střídačů) pojistku nespustí – páry import/export a
  nabíjení/vybíjení platí, když je dostupná aspoň jedna strana, a krátkou
  mezeru překlene poslední dobrá hodnota. Termíny (bojler, auto ráno) běží
  dál, limit přetoku zůstane. Stav „Pojistka – chybí data“, varování v logu.
* **Tlumení proudu auta:** vyšší proud až po 30 s stabilního přebytku, malý
  pokles (do tolerance před vypnutím) po zpoždění vypnutí, velký pokles hned.
* **Jen sledovat:** přepínač, kdy integrace počítá, loguje a zobrazuje, ale nic
  nespíná a nezapisuje limit přetoku. Doporučený první krok na skutečné
  instalaci.

### Statistika spotřeby a nákladů

Každé zařízení má kumulativní entity **Energie**, **Energie ze slunce**,
**Energie z baterie**, **Energie ze sítě** a **Náklady** (Kč). HA z nich sám
počítá denní a měsíční statistiky (panel: grafy po dnech). Atribut `today`
ukazuje dnešní hodnotu, karta „dnes 3,2 kWh · 4,10 Kč · ☀ 65 %“.

* Řízená zařízení jsou zátěže, které se dají posunout, proto se jim odběr ze sítě
  a vybíjení baterie připisuje přednostně (dům bere slunce první).
* Náklady = energie ze sítě × **Cena NT** v HDO, jinak × **Cena VT**. Slunce
  a baterie se počítají zdarma.
* Měří se skutečná spotřeba (nejlépe se senzorem výkonu zařízení), takže to
  funguje i v režimu Jen sledovat. Statistiky přežijí restart.

Ceny NT/VT (krok HDO v průvodci nebo entity) slouží jen pro zobrazení
a statistiku, o rozhodování neovlivňují.

### AI hodnocení

Volitelně každý den (výchozí 21:00) nebo tlačítkem **Vyhodnotit nyní** pošle
FVE Optimizer podklady dne (spotřeba a náklady zařízení, odběr/přetok, spínání,
pojistka, log rozhodnutí, nastavení, předpoklad zbytku dne) libovolné **AI Task**
entitě v HA – Google Gemini, Anthropic Claude, OpenAI, Ollama… AI vrátí známku
1–10, shrnutí, co fungovalo, problémy a **návrhy úprav nastavení**. Sama nic
nemění.

* Nastavení: integrace → **Konfigurovat** → krok Řízení → **AI pro denní hodnocení**.
* Výsledek: entita *AI hodnocení* (známka, text v atributech), panel → záložka
  **Hodnocení** (poslední hodnocení a historie 14 dní), služba
  `fve_optimizer.run_review`.
* Po hodnocení se vždy vypálí event `fve_optimizer_review_done` (score, summary,
  suggestions…). Volitelně notifikace při nízké známce / návrzích.
* **AI rada při riziku termínu**: když bojler/auto začne nestíhat (`at_risk`),
  stejná AI jednou denně na zařízení navrhne krátkou radu
  (event `fve_optimizer_outlook_check` + notifikace).

### Notifikace a eventy

V kroku Řízení (a jako entity) nastavíš:

* **Služba notifikací** – např. `mobile_app_pixel` nebo `telegram` (doména
  `notify.` se doplní). Prázdné = jen trvalé notifikace / eventy.
* **Trvalé notifikace v HA** – Nastavení → Notifikace.
* Přepínače: hodnocení, pojistka, riziko termínu, boost EV, objednávka EV;
  práh známky pro notifikaci po review.

Doménové eventy (vždy, i bez notify služby) – vhodné do automatizací:

| Event | Kdy |
| --- | --- |
| `fve_optimizer_review_done` | po AI hodnocení |
| `fve_optimizer_outlook_check` | AI rada při at_risk |
| `fve_optimizer_failsafe` / `_failsafe_cleared` | vstup / návrat z pojistky |
| `fve_optimizer_deadline_risk` | zařízení začne nestíhat termín |
| `fve_optimizer_boost` | start / konec rychlého nabíjení |
| `fve_optimizer_charge_order` | nastavení / zrušení / splnění objednávky |

### Priority

Každé zařízení má entitu **Priorita**: nižší číslo dostane přebytky dřív
(např. EcoVolter 1, bojler 2 = nejdřív auto). Baterie má vždy přednost do
**Cílového SoC**. Když ho snížíš, dostanou spotřebiče přebytky dřív.

### Teploty bojleru

Se senzorem teploty má bojler dvě nezávislé teploty:

* **Maximální teplota z přebytků** (např. 75 °C): do ní se bojler ohřívá
  z přebytků a ukládá do vody energii, kterou by jinak střídač zahodil. Po
  dosažení maxima se znovu zapne až po poklesu o **Hysterezi maximální teploty**.
* **Teplota v termínu** (např. 50 °C do 19:00): garantované minimum, viz níže.

### Nahřát do termínu (bojler)

Když je u spínaného zařízení zadaný senzor teploty, objeví se na něm:
**Nahřát do termínu** (zap/vyp), **Termín nahřátí** (čas), **Teplota v termínu**,
**Objem nádrže**, **Hystereze termínu** a **Rezerva doby ohřevu**.

Integrace průběžně počítá, jak dlouho by ohřev trval
(`objem × 1,163 Wh/(l·K) × ΔT / příkon × rezerva`), a když už nezbývá víc času,
bojler zapne i bez přebytků (ze sítě nebo z baterie). Během dne ho mezitím
normálně ohřívají přebytky, takže ze sítě se většinou dohřívá jen zbytek.
Ohřev do termínu:

* má přednost před ostatními zařízeními, ale respektuje hlavní jistič,
* pokračuje i po termínu, dokud teplota není dosažena (nejdéle do půlnoci),
* po termínu už nový ohřev nespustí,
* nezvedá limit přetoku.

**Jen v HDO:** když je v integraci nastavené HDO a u bojleru zapnuté **Dohřívat
do termínu jen v HDO**, ohřívá se ze sítě jen v nízkém tarifu.

* S predikcí (Solcast) se ze sítě plánuje jen to, **co nedodá slunce**:
  `slunce pro zařízení = zbývající predikce ÷ koeficient − spotřeba domu do
  západu` (bez „Minimum před baterií“ ještě − dobití baterie). Za slunečného
  dne se ze sítě nic neplánuje (`deadline_mode: solar`), za zataženého jen
  chybějící část (`deadline_grid_kwh`). Predikce se přes den zpřesňuje, plán
  taky.
* Se známým rozvrhem (EG.D, PRE, kalendář, ruční časy) integrace vybere
  **nejpozdější okna HDO před termínem**, která na ohřev stačí. Přebytky tak mají
  co nejvíc času. Plán je v atributu `deadline_plan`, a když okna nestačí,
  `deadline_at_risk` je `true`.
* Jen s entitou zap/vyp (budoucnost neznámá) se dohřívá v každém okně HDO od
  **Dohřev ze sítě nejdříve od** do termínu. Se známým rozvrhem je to jen
  volitelná pojistka (výchozí 00:00 = bez omezení).
* Mimo HDO bojler čeká („Čeká na HDO“). Po termínu se dohřeje v nejbližším
  HDO téhož dne.

Stav je vidět v `sensor.<bojler>_control_state` („Nahřívá do termínu“) a atributy
`deadline_start` a `deadline_heating_h` na `sensor.<bojler>_allocated_power`.

Každé zařízení má přepínač **Řízení**. Když je vypnutý, optimizer zařízení
nechá být. Pokud ho předtím zapnul sám, vypne ho.

## Nastavení

Všechno se nastavuje v integraci, bez YAML:

* **Přiřazené entity** (senzory střídače, spínače, nabíječka): v průvodci
  a v **Konfigurovat** / **Upravit zařízení**. Po změně se integrace znovu načte.
* **Provozní parametry** (cílové SoC, limity přetoku, rezervy, jistič, napětí,
  interval, priority, příkony, proudy, fáze, teploty, zpoždění): jako entity
  `number` / `select` v sekci *Konfigurace* každého zařízení. Stejné hodnoty jsou
  i v průvodci. Změna se projeví hned bez reloadu, takže je můžeš měnit
  i z dashboardu nebo automatizací (např. večer snížit cílové SoC).

## HDO (nízký tarif)

V průvodci (krok **HDO – nízký tarif**, také v **Konfigurovat**) vybereš zdroj:

| Zdroj | Nastavení | Poznámka |
| --- | --- | --- |
| **EG.D** | PSČ + kód HDO (`A1B4DP5`, nebo povel `405`, u chytrého elektroměru `Cd56`) | veřejná data EG.D, obnova každých 6 h |
| **PRE** | povel HDO (nabídka se načte z webu PRE) | veřejná stránka PRE |
| **Kalendář** | libovolný kalendář s událostmi NT | např. integrace ČEZ Distribuce |
| **Entita** | `binary_sensor`, `input_boolean`, `schedule`, `switch` | jen aktuální stav, bez plánu |
| **Ruční časy** | `00:00-06:00; 14:00-17:00`, zvlášť víkend | svátky = víkend |

**ČEZ Distribuce:** anonymní API časů spínání je od roku 2026 chráněné captchou,
proto ho integrace nevolá. Použij kalendář z integrace, která se přihlašuje do
portálu ČEZ Distribuce (např. `konikvranik/hacs_cez_distribuce`), nebo ruční časy.

Při výpadku distributora se použijí poslední stažená okna. Entita
`binary_sensor.fve_optimizer_hdo_low_tariff` ukazuje aktuální tarif a v atributech
okna na dnešek a zítřek, příští změnu a případnou chybu.

## Entity

* `switch.fve_optimizer_optimization`: hlavní vypínač
* `sensor.fve_optimizer_budget` (rozpočet pro zařízení, ne přetok), `…_allocated`, `…_managed`
* `sensor.fve_optimizer_battery_target_soc`, `…_breaker_headroom`, `…_status`
* `binary_sensor.fve_optimizer_battery_priority`, `…_forecast_covers_battery`, `…_export_limit_raised`
* pro každé zařízení: `switch.<zařízení>_control`, `sensor.<zařízení>_allocated_power`,
  `sensor.<zařízení>_control_state`, `binary_sensor.<zařízení>_active`

## Instalace

Zkopíruj `custom_components/fve_optimizer` do `config/custom_components/`
(nebo přidej repozitář do HACS jako vlastní) a restartuj HA.

## Před prvním spuštěním ověř

* **Znaménka**: výkon sítě při odběru a výkon baterie při nabíjení (přepínače
  v prvním kroku průvodce).
* **Jednotku limitu přetoku**: běžný a zvýšený limit musí být ve stejné jednotce
  jako entita v tvé integraci Growattu (W, nebo %).
* **Zápis limitu do EEPROM**: limit se mění jen při změně stavu, typicky pár
  zápisů denně.

## Vývoj

Testy potřebují **Python 3.14** (stejně jako CI / Home Assistant 2026.9).
Systémové `python3` na macOS je často 3.12 — ten balíček
`pytest-homeassistant-custom-component` neinstaluje.

```bash
# jednou: venv z Homebrew Python 3.14
/opt/homebrew/opt/python@3.14/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt

# pak vždy
.venv/bin/pytest -q
```
