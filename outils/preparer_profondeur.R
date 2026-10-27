# Carte de profondeur de sol à 1 km
# =================================
# Rasterise la couche bdgsf_classe_prof (BDGSF 1/1 000 000, champ PR_CL : classe de profondeur
# en cm, 30 / 50 / 100 / 200 ; valeurs négatives = sans donnée) sur la grille de la carte de
# réserve utile allégée (sol/ru_sol_1km.tif, Lambert-93), et l'écrit en mètres dans
# sol/profondeur_sol_1km.tif.
#
#   Rscript outils/preparer_profondeur.R [dossier de l'application]
#
# Requiert les packages sf et terra.

args <- commandArgs(TRUE)
racine <- if (length(args)) args[1] else "."
suppressMessages({ library(sf); library(terra) })

prof <- st_read(file.path(racine, "bdgsf_classe_prof", "bdgsf_classe_prof.shp"), quiet = TRUE)
prof <- st_transform(prof, 2154)
prof$prof_m <- ifelse(prof$PR_CL > 0, prof$PR_CL / 100, NA)

grille <- rast(file.path(racine, "sol", "ru_sol_1km.tif"))
r <- rasterize(vect(prof[!is.na(prof$prof_m), ]), grille, field = "prof_m")
names(r) <- "profondeur_sol_m"
sortie <- file.path(racine, "sol", "profondeur_sol_1km.tif")
writeRaster(r, sortie, overwrite = TRUE, NAflag = -9999, datatype = "FLT4S",
            gdal = c("COMPRESS=DEFLATE", "TILED=YES"))
cat(sortie, ":", round(file.size(sortie) / 1e6, 2), "Mo ;", "valeurs", paste(sort(unique(values(r)[!is.na(values(r))])), collapse = ", "), "m\n")
