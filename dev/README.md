# Vývojové prostředí (Docker)

Home Assistant v Dockeru s integrací načtenou přímo ze zdrojáků a se simulátorem
FVE, baterie, bojleru a EcoVolteru. Slouží k ladění bez skutečného hardwaru.

## Start

```bash
cd dev
docker compose up -d
```

Otevři <http://localhost:8123> a projdi onboarding (lokální účet jen pro vývoj).

Po změně kódu integrace:

```bash
docker compose restart
```

Log (FVE Optimizer je na úrovni debug):

```bash
docker compose logs -f
```

## Přidání integrace se simulátorem

**Nastavení → Zařízení a služby → Přidat integraci → FVE Optimizer**

| Pole | Entita |
| --- | --- |
| Výkon sítě | `sensor.sim_grid_power` (odběr kladný ✔) |
| Výkon baterie | `sensor.sim_battery_power` (nabíjení kladné ✔) |
| SoC baterie | `sensor.sim_battery_soc` |
| Výkon FV | `sensor.sim_pv_power` |
| Zbývající predikce dnes | `sensor.sim_forecast_remaining_today` |
| Kapacita baterie | 10 kWh |
| Entita limitu přetoku | `input_number.sim_export_limit` v % (běžný 0, zvýšený 100) |
| Řídit limit přetoku | zapnuto (vypni, pokud chceš limit nastavit jednou ručně) |
| Senzory proudu fází | `sensor.sim_current_l1`, `…_l2`, `…_l3` |
| HDO – nízký tarif | `input_boolean.sim_hdo` |

Pak na integraci **Přidat spínané zařízení**:

| Pole | Entita / hodnota |
| --- | --- |
| Spínač | `input_boolean.sim_boiler` |
| Příkon | 2000 W, 1 fáze |
| Senzor výkonu | `sensor.sim_boiler_power` |
| Teplota vody | `sensor.sim_water_temperature` |

A **Přidat nabíječku EV**:

| Pole | Entita |
| --- | --- |
| Spínač nabíjení | `input_boolean.sim_ev_charge` |
| Nabíjecí proud | `input_number.sim_ev_current` |
| Přepínač 3 fází | `input_boolean.sim_ev_3phase` |
| Senzor výkonu | `sensor.sim_ev_power` |
| Auto připojeno | `binary_sensor.sim_ev_connected` |
| SoC auta | `sensor.sim_ev_soc` (pro termín / objednávku / zobrazení na kartě) |

## Dashboard „Simulátor“

V postranním panelu jsou dvě položky:

* **FVE Optimizer**: panel přímo z integrace (stejný jako v produkci), se
  záložkami Přehled, Historie, Statistiky a Nastavení.
* **Simulátor**: jen pro vývoj. Posuvníky simulátoru, vedle reakce optimizeru
  (souhrn, zařízení, doporučení) a řízení s logem rozhodnutí.

Simulátor se generuje z registru entit (ID závisí na jazyku a oblastech). Po
přidání zařízení ho přegeneruj a obnov stránku:

```bash
docker exec -i fve-optimizer-dev python3 - < make_dashboard.py
```

## Co zkoušet

Ovládáš posuvníky **Sim: …**:

* **Dostupná FV výroba**: kolik by panely daly bez omezení. Při plné baterii
  a limitu 0 je výroba oříznutá. Sleduj, jak integrace zvedne limit a přebytek
  se ukáže.
* **Spotřeba domu**: skoky spotřeby (varná konvice) a reakce EV nebo bojleru.
* **SoC baterie**: přednost baterie pod cílovým SoC.
* **Zbývající predikce**: snížení cílového SoC při dobré predikci.
* **Zrychlení času**: jak rychle se nabíjí baterie a ohřívá voda (× reálný čas).
* **Teplota vody**: maximální teplota z přebytků a nahřátí do termínu.
* **Auto připojeno**: start a stop nabíjení.
* **HDO**: dohřev bojleru do termínu jen v nízkém tarifu.

Zjednodušení simulátoru: střídač reaguje okamžitě, bez zpoždění a šumu
skutečného Growattu a Modbusu. Konečné ladění časů a rezerv proto proběhne až
na reálné instalaci.
