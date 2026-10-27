# Kc mensuels des jeux de cultures SB2023 du package CropWat (calés pour MAELIA, bassin de l'Aveyron)
# =================================================================================================
#   Rscript outils/kc_sb2023.R <fichier csv de sortie>
#
# Pour chaque jeu, Kc journalier (courbe FAO par stades, date de semis du jeu) moyenné par mois civil,
# jours hors cycle comptés à 0 ; profondeur racinaire maximale (Zend) et fraction p au stade
# de pleine végétation (p_mid). Utilisé par outils/appliquer_kc_sb2023.py.

.libPaths(c(file.path(Sys.getenv("LOCALAPPDATA"), "R/win-library/4.5"), .libPaths()))
suppressMessages(library(CropWat))
sortie <- commandArgs(TRUE)[1]
jeux <- c("SB2023-maisT", "SB2023-tour", "SB2023-soja", "SB2023-colza", "SB2023-CP")
dates <- seq(as.Date("2001-01-01"), as.Date("2001-12-31"), by = "day")
lignes <- lapply(jeux, function(code) {
  cp <- get_crop_params(code)
  kc <- calc_Kc(cp, DatesR = dates) * calc_isCycle(cp, DatesR = dates)
  kc_m <- tapply(kc, as.integer(format(dates, "%m")), mean)
  data.frame(jeu = code, mois = 1:12, kc = round(as.numeric(kc_m), 2), zr_max = cp$Zend, p = cp$p_mid,
             semis = cp$sowing_date, duree = cp$Lini + cp$Ldev + cp$Lmid + cp$Lend)
})
write.csv(do.call(rbind, lignes), sortie, row.names = FALSE)
