# Comparaison avec le package R CropWat (INRAE) — appelé par outils/comparer_modeles.py
# ==================================================================================
#   Rscript outils/cropwat_comparaison.R <dossier validation>
#
# Lit entrees_cas.csv, entrees_points.csv et entrees_journal.csv, écrit resultats_cropwat.csv :
# - cw_moteur_* : moteur CropWat (CW_model) alimenté par les entrées journalières de la méthode SGPE
#   (ETc, pluie efficace, TAW, RAW) ; irrigation au seuil RAW, retour à la capacité au champ ;
# - cw_param_*  : CropWat avec ses propres paramètres de culture (CW_create_input), même sol et même
#   climat mensuel réparti sur les jours, pluie brute (défaut du package) ou pluie efficace (USDA S.C.S.).
# Rendement relatif en sec : calc_relative_yield(ETc, ETc_adj, Ky) d'une simulation sans irrigation.

.libPaths(c(file.path(Sys.getenv("LOCALAPPDATA"), "R/win-library/4.5"), .libPaths()))
suppressMessages(library(CropWat))

dossier <- commandArgs(TRUE)[1]
cas <- read.csv(file.path(dossier, "entrees_cas.csv"), encoding = "UTF-8", stringsAsFactors = FALSE)
pts <- read.csv(file.path(dossier, "entrees_points.csv"), encoding = "UTF-8", stringsAsFactors = FALSE,
                colClasses = c(point = "character"))
jr <- read.csv(file.path(dossier, "entrees_journal.csv"), encoding = "UTF-8", stringsAsFactors = FALSE)
cas$point <- as.character(cas$point)

# Simulation jour par jour avec le moteur du package (CW_model), sur des vecteurs simples
simuler <- function(ETc, P, TAW, RAW, isCycle, FUN_IRRIG) {
  X <- CW_create_state(Dr = 0, isCycle = isCycle[1], TAW = TAW[1])
  n <- length(ETc); Ir <- numeric(n); ETa <- numeric(n)
  for (i in seq_len(n)) {
    o <- CW_model(X, list(ETc = ETc[i], P = P[i], TAW = TAW[i], RAW = RAW[i], isCycle = isCycle[i], cycle_id = 1),
                  FUN_IRRIG = FUN_IRRIG)
    X <- attr(o, "state"); Ir[i] <- o[["Ir"]]; ETa[i] <- o[["ETc_adj"]]
  }
  list(Ir = Ir, ETa = ETa)
}
irrig_raw <- CW_irrig_fun_factory(RAW_ratio = 1, apply_Dr = TRUE)
peff <- function(p) ifelse(p <= 250, p * (125 - 0.2 * p) / 125, 125 + 0.1 * p)
dates <- seq(as.Date("2001-01-01"), as.Date("2002-12-31"), by = "day")
jours_mois <- as.integer(format(dates, "%m"))
ndj <- c(31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

res <- vector("list", nrow(cas))
for (k in seq_len(nrow(cas))) {
  cs <- cas[k, ]
  # --- 1. Même moteur, mêmes entrées journalières que SGPE
  j <- jr[jr$cle == cs$cle, ]
  m1 <- simuler(j$etc, j$peff, j$taw, j$raw, rep(TRUE, nrow(j)), irrig_raw)
  m0 <- simuler(j$etc, j$peff, j$taw, j$raw, rep(TRUE, nrow(j)), CW_irrig_0)
  # --- 2. Paramètres de culture propres à CropWat
  pt <- pts[pts$point == cs$point, ]
  # unname : des vecteurs nommés renommeraient les sorties de CW_model (ETc_adj.etp_05…)
  etp <- unname(unlist(pt[sprintf("etp_%02d", 1:12)])); pl <- unname(unlist(pt[sprintf("p_%02d", 1:12)]))
  cp <- get_crop_params(cs$code_cropwat)
  semis <- if (nzchar(cs$semis)) cs$semis else cp$sowing_date
  cp$Ytot <- cs$ky; cp$Yini <- cp$Ydev <- cp$Ymid <- cp$Yend <- cs$ky
  fenetre <- dates >= as.Date(paste0("2001-", semis)) & dates < as.Date(paste0("2002-", semis))
  sorties <- list()
  for (variante in c("brute", "peff")) {
    P <- (if (variante == "brute") pl else peff(pl))[jours_mois] / ndj[jours_mois]
    x <- suppressMessages(CW_create_input(cs$code_cropwat, DatesR = dates, ETo = etp[jours_mois] / ndj[jours_mois],
                                          P = P, soil_depth = cs$profondeur, AWC = cs$ru, cp = cp, sowing_date = semis))
    s1 <- simuler(x$ETc, x$P, x$TAW, x$RAW, x$isCycle, irrig_raw)
    sel <- fenetre & x$isCycle
    sorties[[variante]] <- sum(s1$Ir[sel])
    if (variante == "brute") {
      s0 <- simuler(x$ETc, x$P, x$TAW, x$RAW, x$isCycle, CW_irrig_0)
      rel <- calc_relative_yield(x$ETc[sel], s0$ETa[sel], cs$ky)
    }
  }
  res[[k]] <- data.frame(cle = cs$cle, cw_moteur_besoin = round(sum(m1$Ir), 1),
                         cw_moteur_rel_sec = round(max(0, calc_relative_yield(j$etc, m0$ETa, cs$ky)), 3),
                         cw_param_besoin_brute = round(sorties$brute, 1), cw_param_besoin_peff = round(sorties$peff, 1),
                         cw_param_rel_sec = round(max(0, rel), 3))
  if (k %% 25 == 0) cat(k, "/", nrow(cas), "\n")
}
write.csv(do.call(rbind, res), file.path(dossier, "resultats_cropwat.csv"), row.names = FALSE, fileEncoding = "UTF-8")
cat("CropWat : ", nrow(cas), " cas simulés\n")
