"""Génération de factures PDF (pro forma) avec fpdf2."""

from fpdf import FPDF

_OR = (201, 169, 110)
_NOIR = (26, 26, 26)
_GRIS = (100, 100, 100)
_SURFACE = (250, 249, 246)
_BLANC = (255, 255, 255)


def generer_facture_pdf(commande, client=None) -> bytes:
    """Retourne les bytes du PDF de facture pro forma pour `commande`."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    # ── En-tête ───────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(*_OR)
    pdf.cell(0, 13, "ASCALE", new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRIS)
    pdf.cell(0, 5, "Importateur de marbres, granits, onyx et pierres naturelles de prestige",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 5, "Zone Industrielle Oukacha, Casablanca, Maroc",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 5, "contact@ascale.ma   |   +212 5 22 XX XX XX   |   www.ascale.ma",
             new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_draw_color(*_OR)
    pdf.set_line_width(0.8)
    y = pdf.get_y() + 5
    pdf.line(15, y, 195, y)
    pdf.ln(10)

    # ── Titre ─────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*_NOIR)
    pdf.cell(0, 10, f"FACTURE PRO FORMA  -  N° ASC-{commande.id:04d}",
             new_x="LMARGIN", new_y="NEXT", align="C")

    date_str = (commande.date.strftime("%d/%m/%Y") if hasattr(commande.date, "strftime")
                else str(commande.date))
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRIS)
    pdf.cell(0, 6, f"Date : {date_str}    -    Statut : {commande.statut}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(9)

    # ── Infos client ──────────────────────────────────────────────
    pdf.set_fill_color(*_SURFACE)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_OR)
    pdf.cell(0, 9, "  INFORMATIONS CLIENT", fill=True, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_NOIR)
    pdf.ln(1)
    pdf.cell(0, 6, f"  Nom : {commande.client_nom}", new_x="LMARGIN", new_y="NEXT")
    if client:
        if client.email:
            pdf.cell(0, 6, f"  Email : {client.email}", new_x="LMARGIN", new_y="NEXT")
        if client.telephone:
            pdf.cell(0, 6, f"  Téléphone : {client.telephone}", new_x="LMARGIN", new_y="NEXT")
        if client.adresse:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, f"  Adresse de livraison : {client.adresse}")
    pdf.ln(7)

    # ── Tableau produits ──────────────────────────────────────────
    pdf.set_fill_color(*_SURFACE)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_OR)
    pdf.cell(0, 9, "  DÉTAIL DE LA COMMANDE", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    col_w = [88, 28, 36, 28]
    headers = ["Produit", "Qté (m²)", "Prix unit. MAD", "Total MAD"]
    aligns = ["L", "C", "R", "R"]

    pdf.set_fill_color(*_NOIR)
    pdf.set_text_color(*_BLANC)
    pdf.set_font("Helvetica", "B", 9)
    for w, h, a in zip(col_w, headers, aligns):
        pdf.cell(w, 8, h, fill=True, align=a, new_x="RIGHT", new_y="TOP")
    pdf.ln(8)

    fill = False
    for ligne in commande.lignes:
        pdf.set_fill_color(*(_SURFACE if fill else _BLANC))
        pdf.set_text_color(*_NOIR)
        pdf.set_font("Helvetica", "", 9)
        st = ligne.quantite * ligne.prix_unitaire
        vals = [
            ligne.produit_nom,
            str(ligne.quantite),
            f"{ligne.prix_unitaire:,.0f}",
            f"{st:,.0f}",
        ]
        for w, v, a in zip(col_w, vals, aligns):
            pdf.cell(w, 7, v, fill=True, align=a, new_x="RIGHT", new_y="TOP")
        pdf.ln(7)
        fill = not fill

    # ── Total ─────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_draw_color(*_OR)
    pdf.set_line_width(0.4)
    x_sep = 15 + col_w[0] + col_w[1]
    pdf.line(x_sep, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_NOIR)
    pdf.cell(col_w[0] + col_w[1] + col_w[2], 9, "TOTAL HT :", align="R",
             new_x="RIGHT", new_y="TOP")
    pdf.set_text_color(*_OR)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(col_w[3], 9, f"{commande.total:,.0f} MAD", align="R",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    # ── Note légale ───────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_GRIS)
    pdf.multi_cell(0, 5, (
        "FACTURE PRO FORMA - Aucun débit en ligne n'a été effectué. "
        "Notre équipe vous contactera pour confirmer les modalités de règlement "
        "(virement bancaire, chèque certifié ou espèces au showroom). "
        "Un acompte de 30 % est demandé à la confirmation. "
        "Prix en MAD HT. Livraison et pose non incluses sauf accord préalable écrit."
    ))

    # ── Pied de page ──────────────────────────────────────────────
    # Auto page break désactivé ici : sans ça, set_y(-18) atterrit pile sur
    # le seuil de marge (18) et fpdf2 insère une 2e page pour le pied de page.
    pdf.set_auto_page_break(auto=False)
    pdf.set_y(-18)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 5,
             "Ascale - Casablanca, Maroc - contact@ascale.ma - +212 5 22 XX XX XX",
             align="C")

    return bytes(pdf.output())
