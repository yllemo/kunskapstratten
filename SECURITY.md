# Säkerhet

## Rapportera en sårbarhet

Publicera inte exploateringsdetaljer eller känsliga exempeldata i ett öppet
GitHub-ärende. Kontakta projektets ansvariga privat via GitHub-profilens
kontaktväg och beskriv berörd version, påverkan och reproduktionssteg.

## Säkerhetsmodell

Kunskapstratten är avsedd att köras lokalt och binder som standard endast till
`127.0.0.1`. Webbgränssnittet har ingen autentisering. Bind därför inte till
`0.0.0.0` eller exponera porten mot ett nätverk utan ett separat, korrekt
konfigurerat autentiserings- och TLS-lager.

Importerade dokument kan innehålla känslig information. Mapparna `inbox/`,
`processed/`, `kunskapsbank/`, `data/` och `logs/` ignoreras därför som
standard av Git, med undantag för uttryckligen sanerade exempel och tomma
platshållarfiler.

AI-baserad pseudonymisering är inte en garanti för anonymisering. Den
medföljande fornnordiska demoskillen får inte användas som produktionsmässigt
integritets- eller regelefterlevnadsskydd.
