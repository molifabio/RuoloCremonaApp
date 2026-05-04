# Quiz mappa Cremona (Python)

App in Streamlit per allenarti sui punti di interesse di Cremona con due modalita.

## Modalita disponibili

1. Quiz 10 POI
- uno alla volta viene mostrato il nome di un punto
- clicchi la mappa (aggancio automatico al POI piu vicino)
- confermi e passi alla domanda successiva
- alla fine ottieni il resoconto dei corretti

2. Percorsi 5 round
- per ogni round vengono evidenziati 2 POI (partenza/arrivo)
- inserisci il nome di una strada e la evidenzi in mappa
- confermi il tentativo (con controllo automatico approssimato di compatibilita)
- al termine vedi il resoconto dei 5 tentativi

## Requisiti

- Python 3.10+ consigliato

## Avvio rapido (PowerShell)

```powershell
cd "c:\Users\Utente\Desktop\Casa\RUOLO\Cremona"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Come personalizzare i punti

Modifica `poi_cremona.json`.
Ogni voce deve avere:

```json
{
  "name": "Nome punto",
  "lat": 45.00000,
  "lon": 10.00000
}
```

Nota: i marker sono volutamente anonimi (Punto #1, Punto #2, ...), cosi il quiz resta utile.

## Nota tecnica sulla modalita percorsi

La verifica della strada e approssimata e usa OpenStreetMap (Nominatim):
- il nome strada inserito viene cercato e mostrato in mappa quando disponibile
- la compatibilita viene confrontata con un set di strade rilevate lungo il corridoio tra i due POI

Questa verifica non sostituisce un vero motore di routing stradale, ma e utile per allenamento.



Salve, quest'anno purtroppo abbiamo avuto problemi nella compilazione dell'isee, e siamo in ritardo. Qual'ora sottoscrivessi l'isee in questi giorni si può aggiornare l'importo della seconda rata?