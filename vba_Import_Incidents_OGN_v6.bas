Option Explicit

' ==================================================================
'  SMART-SUP | Import incidents Outlook -> Excel  (v6)
' ------------------------------------------------------------------
'  NOUVEAUTES v6 par rapport a la v5 :
'
'  1. FUSION PAR TICKET : un incident = UNE ligne, meme si plusieurs
'     mails le concernent (avis de debut, avis de fin, regularisation).
'     Les mails sont traites par ordre chronologique et se completent.
'
'  2. STATUT DEDUIT DE LA DONNEE, PAS DU SUJET.
'     La v5 lisait le mot "FIN" dans le sujet. Or un incident resolu
'     AVANT la communication initiale donne lieu a l'envoi d'un avis
'     de debut ET d'un avis de fin : le statut doit donc venir de la
'     presence effective d'une heure de fin, pas du libelle du sujet.
'
'  3. BUG CORRIGE - perimetre impacte.
'     Le motif v5 "Service\s*impact.*" ne reconnaissait que
'     "Service impacte" au singulier. Il echouait sur
'     "Services impactes" (RAN) et "Liens Impactes" (NBN),
'     laissant la colonne E vide pour la majorite des mails.
'     Motif v6 : "(Service|Lien)s?\s*impact.*"
'
'  4. BUG CORRIGE - champ Cause qui deborde.
'     Sur un avis de debut il n'y a pas de ligne "Action" : la balise
'     de fin etait introuvable et la Cause avalait tout le reste du
'     mail (perimetre, observation, signature). Les balises de fin
'     sont desormais des alternatives : on s'arrete a la premiere
'     rencontree.
'
'  5. RELANCE SANS DOUBLON : les tickets deja presents dans la feuille
'     sont mis a jour sur place au lieu d'etre re-ajoutes.
'
'  6. COLONNES MANUELLES PRESERVEES : TMC, SLA, Exclusion et RI ne
'     sont jamais ecrasees si elles ont ete renseignees a la main.
'
'  7. FEUILLE "Log_Import" : trace des anomalies (mails sans
'     reference, ecarts de reference entre sujet et corps,
'     regularisations detectees).
' ------------------------------------------------------------------
'  MAPPING DES COLONNES (feuille "Incidents") - 21 colonnes :
'   A: N                     H: Fin reparation        O: Actions correctives
'   B: N ticket              I: Duree retab (hh:mn)   P: TMC
'   C: Priorite              J: Duree retab (mn)      Q: Statut
'   D: Origine               K: Duree repar (hh:mn)   R: Observation
'   E: Nom de service        L: Duree repar (mn)      S: SLA
'   F: Debut                 M: Description           T: Exclusion
'   G: Fin retablissement    N: Cause de l'incident   U: RI
' ------------------------------------------------------------------
'  ENCODAGE : tout le CODE est en ASCII pur.
'    - les balises accentuees sont ecrites en motifs ( "D.but" )
'    - les libelles accentues sont generes par ChrW() a l'execution
'  => le module s'importe correctement quel que soit l'encodage.
' ==================================================================


' ---------- Parametres ----------
Private Const NOM_BAL       As String = "Incidentmanagement.Smc.OGC@orange-sonatel.com"
Private Const NOM_DOSSIER   As String = "Export_cupure"
Private Const NOM_FEUILLE   As String = "Incidents"
Private Const NOM_LOG       As String = "Log_Import"

' ---------- Colonnes ----------
Private Const C_NUM         As Long = 1
Private Const C_TICKET      As Long = 2
Private Const C_PRIORITE    As Long = 3
Private Const C_ORIGINE     As Long = 4
Private Const C_SERVICE     As Long = 5
Private Const C_DEBUT       As Long = 6
Private Const C_FINRETAB    As Long = 7
Private Const C_FINREPAR    As Long = 8
Private Const C_DURRETHM    As Long = 9
Private Const C_DURRETMN    As Long = 10
Private Const C_DURREPHM    As Long = 11
Private Const C_DURREPMN    As Long = 12
Private Const C_DESCRIPTION As Long = 13
Private Const C_CAUSE       As Long = 14
Private Const C_ACTION      As Long = 15
Private Const C_TMC         As Long = 16
Private Const C_STATUT      As Long = 17
Private Const C_OBSERVATION As Long = 18
Private Const C_SLA         As Long = 19
Private Const C_EXCLUSION   As Long = 20
Private Const C_RI          As Long = 21

' ---------- Motifs de balises ----------
' Le point remplace les caracteres accentues (voir note d'encodage).
Private Const M_PERIMETRE   As String = "(Service|Lien)s?\s*impact.*"
Private Const M_FIN_DESC    As String = "(D.but|TT\s*&\s*priorit.*)"
Private Const M_FIN_DEBUT   As String = "(Fin|TT\s*&\s*priorit.*)"
Private Const M_FIN_FINRET  As String = "(TT\s*&\s*priorit.*|Cause)"
Private Const M_FIN_CAUSE   As String = "(Action|(Service|Lien)s?\s*impact.*|Observation)"
Private Const M_FIN_ACTION  As String = "((Service|Lien)s?\s*impact.*|Observation)"
Private Const M_FIN_PERIM   As String = "(Observation|Cordialement.*)"
Private Const M_FIN_OBS     As String = "Cordialement.*"


' ==================================================================
'  PROCEDURE PRINCIPALE
' ==================================================================
Public Sub Import_Incidents_OGN()

    Dim olApp As Object, olNs As Object
    Dim Mailbox As Object, Dossier As Object
    Dim itms As Object, itm As Object
    Dim WS As Object
    Dim dicInc As Object, dicLignes As Object
    Dim Journal As Collection

    Set dicInc = CreateObject("Scripting.Dictionary")
    Set Journal = New Collection

    ' --- Feuille de destination ---
    Set WS = ObtenirFeuille(NOM_FEUILLE)
    EcrireEntetes WS
    Set dicLignes = LireTicketsExistants(WS)

    ' --- Connexion Outlook ---
    On Error Resume Next
    Set olApp = GetObject(, "Outlook.Application")
    If olApp Is Nothing Then Set olApp = CreateObject("Outlook.Application")
    On Error GoTo 0

    If olApp Is Nothing Then
        MsgBox "Impossible de demarrer ou de se connecter a Outlook.", vbCritical
        Exit Sub
    End If

    Set olNs = olApp.GetNamespace("MAPI")

    On Error Resume Next
    Set Mailbox = olNs.Folders(NOM_BAL)
    On Error GoTo 0

    If Mailbox Is Nothing Then
        Dim noms As String, f As Object
        On Error Resume Next
        For Each f In olNs.Folders
            noms = noms & vbCrLf & " - " & f.Name
        Next f
        On Error GoTo 0
        MsgBox "Boite mail introuvable : " & NOM_BAL & vbCrLf & _
               "Verifiez qu'elle est bien ajoutee dans votre profil Outlook." & vbCrLf & vbCrLf & _
               "Boites disponibles dans votre profil :" & noms, vbCritical
        Exit Sub
    End If

    Set Dossier = TrouverDossier(Mailbox, NOM_DOSSIER)

    If Dossier Is Nothing Then
        Dim nomsD As String, sf As Object
        On Error Resume Next
        For Each sf In Mailbox.Folders
            nomsD = nomsD & vbCrLf & " - " & sf.Name
        Next sf
        On Error GoTo 0
        MsgBox "Sous-dossier '" & NOM_DOSSIER & "' introuvable dans la boite partagee." & vbCrLf & _
               "Verifiez le nom exact du dossier." & vbCrLf & vbCrLf & _
               "Sous-dossiers disponibles :" & nomsD, vbCritical
        Exit Sub
    End If

    ' --- PASSE 1 : collecte et fusion par ticket ---
    Set itms = Dossier.Items
    On Error Resume Next
    itms.Sort "[ReceivedTime]", False          ' du plus ancien au plus recent
    On Error GoTo 0

    Dim NbMails As Long, NbRetenus As Long, NbErreurs As Long
    NbMails = 0: NbRetenus = 0: NbErreurs = 0

    For Each itm In itms
        If TypeName(itm) = "MailItem" Then
            NbMails = NbMails + 1
            If EstMailIncident(itm.Subject) Then
                On Error Resume Next
                CollecterMail itm, dicInc, Journal
                If Err.Number <> 0 Then
                    NbErreurs = NbErreurs + 1
                    Journal.Add "Erreur de traitement : " & UneLigne(itm.Subject) & _
                                " (" & Err.Description & ")"
                    Err.Clear
                Else
                    NbRetenus = NbRetenus + 1
                End If
                On Error GoTo 0
            End If
        End If
    Next itm

    ' --- PASSE 2 : ecriture / mise a jour de la feuille ---
    Dim NbNouveaux As Long, NbMaj As Long
    NbNouveaux = 0: NbMaj = 0
    EcrireIncidents WS, dicInc, dicLignes, NbNouveaux, NbMaj

    ' --- Mise en forme des colonnes de dates ---
    On Error Resume Next
    WS.Columns(C_DEBUT).NumberFormat = "dd/mm/yyyy hh:mm"
    WS.Columns(C_FINRETAB).NumberFormat = "dd/mm/yyyy hh:mm"
    WS.Columns(C_FINREPAR).NumberFormat = "dd/mm/yyyy hh:mm"
    On Error GoTo 0

    ' --- Journal ---
    EcrireJournal Journal, NbMails, NbRetenus, dicInc.Count, NbNouveaux, NbMaj

    ' --- Bilan ---
    Dim Msg As String
    Msg = "Import termine." & vbCrLf & vbCrLf & _
          "Mails parcourus      : " & NbMails & vbCrLf & _
          "Mails d'incident     : " & NbRetenus & vbCrLf & _
          "Incidents distincts  : " & dicInc.Count & vbCrLf & _
          "Nouvelles lignes     : " & NbNouveaux & vbCrLf & _
          "Lignes mises a jour  : " & NbMaj

    If Journal.Count > 0 Then
        Msg = Msg & vbCrLf & vbCrLf & Journal.Count & " anomalie(s) : voir la feuille '" & NOM_LOG & "'."
    End If
    If NbErreurs > 0 Then
        Msg = Msg & vbCrLf & NbErreurs & " mail(s) n'ont pas pu etre traites."
    End If

    MsgBox Msg, IIf(Journal.Count > 0 Or NbErreurs > 0, vbExclamation, vbInformation)

End Sub


' ==================================================================
'  COLLECTE ET FUSION
' ==================================================================

' Extrait un mail et fusionne son contenu dans le dictionnaire des
' incidents, sous la cle "reference de ticket".
Private Sub CollecterMail(Mail As Object, dicInc As Object, Journal As Collection)

    Dim Corps As String, Sujet As String
    Corps = Mail.Body
    Sujet = Mail.Subject

    ' --- Reference : le corps fait foi, le sujet sert de repli ---
    Dim RefCorps As String, RefSujet As String, Ref As String
    RefCorps = ExtraireTicket(Corps)
    RefSujet = ExtraireTicket(Sujet)

    Ref = RefCorps
    If Ref = "N/A" Then Ref = RefSujet

    If Ref = "N/A" Then
        Journal.Add "Mail sans reference de ticket, ignore : " & UneLigne(Sujet)
        Exit Sub
    End If

    If RefSujet <> "N/A" And RefCorps <> "N/A" And RefSujet <> RefCorps Then
        Journal.Add "Ecart de reference (sujet=" & RefSujet & " / corps=" & RefCorps & _
                    ") - retenu : " & Ref & " | " & UneLigne(Sujet)
    End If

    ' --- Enregistrement de l'incident (cree si absent) ---
    Dim d As Object
    If dicInc.Exists(Ref) Then
        Set d = dicInc(Ref)
    Else
        Set d = NouvelIncident(Ref)
        dicInc.Add Ref, d
    End If

    d("nbmails") = d("nbmails") + 1

    If EstRegularisation(Sujet) Then
        If d("regul") = False Then
            d("regul") = True
            Journal.Add "Regularisation detectee pour le ticket " & Ref & " | " & UneLigne(Sujet)
        End If
    End If

    ' --- Champs texte ---
    Dim Prio As String, Desc As String
    Dim Cause As String, Action As String, Perim As String, Obs As String

    Prio = ExtrairePriorite(Corps)
    If Prio = "N/A" Then Prio = ExtrairePriorite(Sujet)

    Desc = UneLigne(ChampSouple(Corps, "Description", M_FIN_DESC))
    If Desc = "N/A" Then Desc = UneLigne(NettoyerSujet(Sujet))

    Cause = UneLigne(ChampSouple(Corps, "Cause", M_FIN_CAUSE))
    Action = UneLigne(ChampSouple(Corps, "Action", M_FIN_ACTION))
    Perim = UneLigne(ChampSouple(Corps, M_PERIMETRE, M_FIN_PERIM))
    Obs = UneLigne(ChampSouple(Corps, "Observation", M_FIN_OBS))

    ' --- Dates ---
    Dim DDebut As Date, DFinRetab As Date, DFinRepar As Date
    DDebut = ConversionDate(ChampSouple(Corps, "D.but", M_FIN_DEBUT))
    DFinRetab = ConversionDate(ChampSouple(Corps, "Fin", M_FIN_FINRET))

    Dim TxtRepar As String
    TxtRepar = ExtraireInline(Corps, "Fin\s*r.paration")
    If TxtRepar = "N/A" Then TxtRepar = ExtraireInline(Corps, "R.paration")
    DFinRepar = ConversionDate(TxtRepar)

    ' --- Fusion ---
    ' Premiere valeur connue : identite de l'incident, stable dans le temps.
    PoserSiVide d, "priorite", Prio
    PoserSiVide d, "description", Desc
    PoserSiVide d, "perimetre", Perim

    ' Derniere valeur connue : l'avis de fin corrige et complete l'avis
    ' de debut (cause affinee, action realisee, observation finale).
    PoserSiRenseigne d, "cause", Cause
    PoserSiRenseigne d, "action", Action
    PoserSiRenseigne d, "observation", Obs

    ' Debut : on garde la date la plus ancienne rencontree.
    If DDebut <> 0 Then
        If d("debut") = 0 Or CDbl(DDebut) < d("debut") Then d("debut") = CDbl(DDebut)
    End If

    ' Fin : on garde la date la plus recente rencontree.
    If DFinRetab <> 0 Then
        If CDbl(DFinRetab) > d("finretab") Then d("finretab") = CDbl(DFinRetab)
    End If
    If DFinRepar <> 0 Then
        If CDbl(DFinRepar) > d("finrepar") Then d("finrepar") = CDbl(DFinRepar)
    End If

End Sub


' Cree un enregistrement d'incident vide.
Private Function NouvelIncident(Ref As String) As Object
    Dim d As Object
    Set d = CreateObject("Scripting.Dictionary")
    d("ref") = Ref
    d("priorite") = "N/A"
    d("description") = "N/A"
    d("perimetre") = "N/A"
    d("cause") = "N/A"
    d("action") = "N/A"
    d("observation") = "N/A"
    d("debut") = CDbl(0)
    d("finretab") = CDbl(0)
    d("finrepar") = CDbl(0)
    d("nbmails") = 0
    d("regul") = False
    Set NouvelIncident = d
End Function


' Ecrit la valeur seulement si la cle est encore vide.
Private Sub PoserSiVide(d As Object, Cle As String, Valeur As String)
    If EstVide(CStr(d(Cle))) And Not EstVide(Valeur) Then d(Cle) = Valeur
End Sub


' Ecrit la valeur des lors qu'elle est renseignee (la derniere gagne).
Private Sub PoserSiRenseigne(d As Object, Cle As String, Valeur As String)
    If Not EstVide(Valeur) Then d(Cle) = Valeur
End Sub


Private Function EstVide(s As String) As Boolean
    EstVide = (Trim(s) = "" Or StrComp(Trim(s), "N/A", vbTextCompare) = 0)
End Function


' ==================================================================
'  ECRITURE DANS LA FEUILLE
' ==================================================================

Private Sub EcrireIncidents(WS As Object, dicInc As Object, dicLignes As Object, _
                            ByRef NbNouveaux As Long, ByRef NbMaj As Long)

    Dim DerniereLigne As Long, LigneLibre As Long, MaxNum As Long, r As Long
    DerniereLigne = WS.Cells(WS.Rows.Count, C_TICKET).End(xlUp).Row
    If DerniereLigne < 1 Then DerniereLigne = 1

    MaxNum = 0
    For r = 2 To DerniereLigne
        If IsNumeric(WS.Cells(r, C_NUM).Value) Then
            If CLng(WS.Cells(r, C_NUM).Value) > MaxNum Then MaxNum = CLng(WS.Cells(r, C_NUM).Value)
        End If
    Next r

    LigneLibre = DerniereLigne + 1
    If LigneLibre < 2 Then LigneLibre = 2

    Dim k As Variant, d As Object, L As Long
    For Each k In dicInc.Keys
        Set d = dicInc(k)

        If dicLignes.Exists(k) Then
            L = CLng(dicLignes(k))
            FusionnerDepuisFeuille WS, L, d      ' ne jamais perdre l'existant
            NbMaj = NbMaj + 1
        Else
            L = LigneLibre
            LigneLibre = LigneLibre + 1
            MaxNum = MaxNum + 1
            WS.Cells(L, C_NUM).Value = MaxNum
            NbNouveaux = NbNouveaux + 1
        End If

        EcrireLigne WS, L, d
    Next k

End Sub


' Recupere dans l'enregistrement ce que la feuille contient deja et que
' les mails de cette execution n'ont pas fourni. Evite qu'une relance
' partielle efface des donnees importees precedemment.
Private Sub FusionnerDepuisFeuille(WS As Object, L As Long, d As Object)

    PoserSiVide d, "priorite", CStr(WS.Cells(L, C_PRIORITE).Value)
    PoserSiVide d, "description", CStr(WS.Cells(L, C_DESCRIPTION).Value)
    PoserSiVide d, "perimetre", CStr(WS.Cells(L, C_SERVICE).Value)
    PoserSiVide d, "cause", CStr(WS.Cells(L, C_CAUSE).Value)
    PoserSiVide d, "action", CStr(WS.Cells(L, C_ACTION).Value)
    PoserSiVide d, "observation", CStr(WS.Cells(L, C_OBSERVATION).Value)

    If d("debut") = 0 Then
        If IsDate(WS.Cells(L, C_DEBUT).Value) Then d("debut") = CDbl(WS.Cells(L, C_DEBUT).Value)
    End If
    If d("finretab") = 0 Then
        If IsDate(WS.Cells(L, C_FINRETAB).Value) Then d("finretab") = CDbl(WS.Cells(L, C_FINRETAB).Value)
    End If
    If d("finrepar") = 0 Then
        If IsDate(WS.Cells(L, C_FINREPAR).Value) Then d("finrepar") = CDbl(WS.Cells(L, C_FINREPAR).Value)
    End If

End Sub


Private Sub EcrireLigne(WS As Object, L As Long, d As Object)

    Dim ea As String
    ea = ChrW(233)                                 ' e accent aigu

    Dim DDebut As Double, DFinRet As Double, DFinRep As Double
    DDebut = d("debut"): DFinRet = d("finretab"): DFinRep = d("finrepar")

    ' --- Durees ---
    Dim RetabOK As Boolean, ReparOK As Boolean
    RetabOK = (DDebut <> 0) And (DFinRet <> 0) And (DFinRet >= DDebut)
    ReparOK = (DDebut <> 0) And (DFinRep <> 0) And (DFinRep >= DDebut)

    Dim DurRetMn As Long, DurRepMn As Long
    Dim DurRetHM As String, DurRepHM As String

    If RetabOK Then
        DurRetMn = DateDiff("n", CDate(DDebut), CDate(DFinRet))
        DurRetHM = FormatDuree(DurRetMn)
    Else
        DurRetHM = "N/A"
    End If

    If ReparOK Then
        DurRepMn = DateDiff("n", CDate(DDebut), CDate(DFinRep))
        DurRepHM = FormatDuree(DurRepMn)
    Else
        DurRepHM = "N/A"
    End If

    ' --- Statut : deduit de la donnee, pas du sujet du mail ---
    '     Un incident resolu avant la communication initiale genere un
    '     avis de debut ET un avis de fin ; seul le fait de disposer
    '     d'une heure de fin permet de conclure qu'il est resolu.
    Dim Statut As String
    If DFinRet <> 0 Then
        Statut = "R" & ea & "solu"
    Else
        Statut = "En cours"
    End If

    ' --- Ecriture ---
    WS.Cells(L, C_TICKET).Value = d("ref")
    WS.Cells(L, C_PRIORITE).Value = d("priorite")
    WS.Cells(L, C_ORIGINE).Value = "Supervision"
    WS.Cells(L, C_SERVICE).Value = d("perimetre")
    WS.Cells(L, C_DEBUT).Value = IIf(DDebut <> 0, CDate(DDebut), "N/A")
    WS.Cells(L, C_FINRETAB).Value = IIf(DFinRet <> 0, CDate(DFinRet), "N/A")
    WS.Cells(L, C_FINREPAR).Value = IIf(DFinRep <> 0, CDate(DFinRep), "N/A")
    WS.Cells(L, C_DURRETHM).Value = DurRetHM
    WS.Cells(L, C_DURRETMN).Value = IIf(RetabOK, DurRetMn, "N/A")
    WS.Cells(L, C_DURREPHM).Value = DurRepHM
    WS.Cells(L, C_DURREPMN).Value = IIf(ReparOK, DurRepMn, "N/A")
    WS.Cells(L, C_DESCRIPTION).Value = d("description")
    WS.Cells(L, C_CAUSE).Value = d("cause")
    WS.Cells(L, C_ACTION).Value = d("action")
    WS.Cells(L, C_STATUT).Value = Statut
    WS.Cells(L, C_OBSERVATION).Value = d("observation")

    ' --- Colonnes renseignees manuellement : ne jamais ecraser ---
    InitialiserSiVide WS, L, C_TMC
    InitialiserSiVide WS, L, C_SLA
    InitialiserSiVide WS, L, C_EXCLUSION
    InitialiserSiVide WS, L, C_RI

End Sub


' Pose "N/A" uniquement si la cellule est encore vide.
Private Sub InitialiserSiVide(WS As Object, L As Long, Col As Long)
    If Trim(CStr(WS.Cells(L, Col).Value)) = "" Then WS.Cells(L, Col).Value = "N/A"
End Sub


' Index des tickets deja presents : reference -> numero de ligne.
Private Function LireTicketsExistants(WS As Object) As Object

    Dim dic As Object
    Set dic = CreateObject("Scripting.Dictionary")

    Dim DerniereLigne As Long, r As Long, Ref As String
    DerniereLigne = WS.Cells(WS.Rows.Count, C_TICKET).End(xlUp).Row

    For r = 2 To DerniereLigne
        Ref = Trim(CStr(WS.Cells(r, C_TICKET).Value))
        If Ref <> "" And StrComp(Ref, "N/A", vbTextCompare) <> 0 Then
            If Not dic.Exists(Ref) Then dic.Add Ref, r
        End If
    Next r

    Set LireTicketsExistants = dic

End Function


Private Function ObtenirFeuille(Nom As String) As Object
    Dim WS As Object
    On Error Resume Next
    Set WS = ThisWorkbook.Sheets(Nom)
    On Error GoTo 0
    If WS Is Nothing Then
        Set WS = ThisWorkbook.Sheets.Add
        WS.Name = Nom
    End If
    Set ObtenirFeuille = WS
End Function


' Ecrit (ou reecrit) la ligne d'en-tete. Les accents sont generes par
' ChrW() pour etre corrects quel que soit l'encodage du fichier.
Private Sub EcrireEntetes(WS As Object)

    Dim dg As String, ea As String
    dg = ChrW(176)   ' symbole degre
    ea = ChrW(233)   ' e accent aigu

    Dim H As Variant
    H = Array( _
        "N" & dg, _
        "N" & dg & " ticket", _
        "Priorit" & ea, _
        "Origine", _
        "Nom de service", _
        "D" & ea & "but", _
        "Fin r" & ea & "tablissement", _
        "Fin r" & ea & "paration", _
        "Dur" & ea & "e r" & ea & "tablissement (hh:mn)", _
        "Dur" & ea & "e r" & ea & "tablissement (mn)", _
        "Dur" & ea & "e r" & ea & "paration (hh:mn)", _
        "Dur" & ea & "e r" & ea & "paration (mn)", _
        "Description", _
        "Cause de l'incident", _
        "Actions correctives", _
        "TMC", _
        "Statut", _
        "Observation", _
        "SLA", _
        "Exclusion", _
        "RI")

    Dim k As Long
    For k = LBound(H) To UBound(H)
        WS.Cells(1, k + 1).Value = H(k)
    Next k
    WS.Rows(1).Font.Bold = True

End Sub


Private Sub EcrireJournal(Journal As Collection, NbMails As Long, NbRetenus As Long, _
                          NbIncidents As Long, NbNouveaux As Long, NbMaj As Long)

    Dim WS As Object
    Set WS = ObtenirFeuille(NOM_LOG)

    Dim L As Long
    L = WS.Cells(WS.Rows.Count, 1).End(xlUp).Row + 1
    If L < 1 Then L = 1

    WS.Cells(L, 1).Value = Now
    WS.Cells(L, 2).Value = "Import : " & NbMails & " mail(s) parcouru(s), " & _
                           NbRetenus & " retenu(s), " & NbIncidents & " incident(s), " & _
                           NbNouveaux & " nouveau(x), " & NbMaj & " mis a jour."
    WS.Cells(L, 2).Font.Bold = True
    L = L + 1

    Dim i As Long
    For i = 1 To Journal.Count
        WS.Cells(L, 1).Value = Now
        WS.Cells(L, 2).Value = Journal(i)
        L = L + 1
    Next i

    On Error Resume Next
    WS.Columns(1).NumberFormat = "dd/mm/yyyy hh:mm:ss"
    WS.Columns(1).ColumnWidth = 18
    WS.Columns(2).ColumnWidth = 110
    On Error GoTo 0

End Sub


' ==================================================================
'  DETECTION / IDENTIFICATION
' ==================================================================

Private Function EstMailIncident(Sujet As String) As Boolean
    EstMailIncident = (InStr(1, UCase(Sujet), "INCIDENT") > 0)
End Function


' "Regularisation" comporte un accent : on utilise un motif tolerant.
Private Function EstRegularisation(Sujet As String) As Boolean
    Dim rx As Object
    Set rx = CreateObject("VBScript.RegExp")
    rx.Pattern = "R.gularisation"
    rx.IgnoreCase = True
    EstRegularisation = rx.Test(Sujet)
End Function


' Retire les prefixes et la reference du sujet pour en faire une
' description de repli lisible.
Private Function NettoyerSujet(Sujet As String) As String
    Dim rx As Object, s As String
    s = Sujet
    Set rx = CreateObject("VBScript.RegExp")
    rx.IgnoreCase = True
    rx.Global = True
    rx.Pattern = "^\s*(RE|TR|FW|FWD)\s*:\s*"
    s = rx.Replace(s, "")
    rx.Pattern = "\|\|.*$"
    s = rx.Replace(s, "")
    NettoyerSujet = Trim(s)
End Function


' ==================================================================
'  FONCTIONS D'EXTRACTION
' ==================================================================

Public Function ExtraireTicket(Texte As String) As String
    Dim RegEx As Object
    Set RegEx = CreateObject("VBScript.RegExp")
    RegEx.Pattern = "\d{4}[A-Za-z]\d{5}"
    RegEx.IgnoreCase = True
    If RegEx.Test(Texte) Then
        ExtraireTicket = UCase(RegEx.Execute(Texte)(0))
    Else
        ExtraireTicket = "N/A"
    End If
End Function


Public Function ExtrairePriorite(Texte As String) As String
    Dim RegEx As Object
    Set RegEx = CreateObject("VBScript.RegExp")
    RegEx.Pattern = "\bP[0-9]\b"
    RegEx.IgnoreCase = True
    If RegEx.Test(Texte) Then
        ExtrairePriorite = UCase(RegEx.Execute(Texte)(0))
    Else
        ExtrairePriorite = "N/A"
    End If
End Function


' Trouve une LIGNE correspondant exactement au motif (espaces et ":"
' finaux toleres). Renvoie {"FirstIndex","Length"} dans le texte source.
Public Function TrouverTag(Texte As String, MotifTag As String, PosDepart As Long) As Object

    If PosDepart > Len(Texte) Then
        Set TrouverTag = Nothing
        Exit Function
    End If

    Dim RegEx As Object
    Set RegEx = CreateObject("VBScript.RegExp")
    RegEx.Pattern = "^[ \t]*" & MotifTag & "[ \t]*:?[ \t]*\r?$"
    RegEx.IgnoreCase = True
    RegEx.Global = True
    RegEx.MultiLine = True

    Dim SousTexte As String
    SousTexte = Mid(Texte, PosDepart)

    Dim Matches As Object
    Set Matches = RegEx.Execute(SousTexte)

    If Matches.Count = 0 Then
        Set TrouverTag = Nothing
    Else
        Dim Res As Object
        Set Res = CreateObject("Scripting.Dictionary")
        Res("FirstIndex") = Matches(0).FirstIndex + (PosDepart - 1)
        Res("Length") = Matches(0).Length
        Set TrouverTag = Res
    End If

End Function


' Contenu compris entre la ligne TagDebut et la ligne TagFin.
' TagFin peut etre une alternative "(A|B|C)" : on s'arrete a la
' premiere balise rencontree, ce qui evite qu'un champ deborde
' lorsqu'une balise attendue est absente du mail.
Public Function ExtraireEntreTags(Texte As String, TagDebut As String, TagFin As String) As String

    Dim MD As Object, MF As Object
    Dim PosDebutContenu As Long, PosFinContenu As Long

    Set MD = TrouverTag(Texte, TagDebut, 1)
    If MD Is Nothing Then
        ExtraireEntreTags = "N/A"
        Exit Function
    End If

    PosDebutContenu = MD("FirstIndex") + MD("Length") + 1

    Set MF = TrouverTag(Texte, TagFin, PosDebutContenu)
    If MF Is Nothing Then
        ExtraireEntreTags = TrimComplet(Mid(Texte, PosDebutContenu))
    Else
        PosFinContenu = MF("FirstIndex") + 1
        ExtraireEntreTags = TrimComplet(Mid(Texte, PosDebutContenu, PosFinContenu - PosDebutContenu))
    End If

    If ExtraireEntreTags = "" Then ExtraireEntreTags = "N/A"

End Function


' Extraction "en ligne" : libelle ET valeur sur la meme ligne
' (ex : "Debut : 06/08/2026 10:55").
Public Function ExtraireInline(Texte As String, MotifLabel As String) As String

    Dim RegEx As Object
    Set RegEx = CreateObject("VBScript.RegExp")
    RegEx.Pattern = "^[ \t]*" & MotifLabel & "[ \t]*[:=][ \t]*(.+?)[ \t]*\r?$"
    RegEx.IgnoreCase = True
    RegEx.Global = True
    RegEx.MultiLine = True

    Dim Matches As Object
    Set Matches = RegEx.Execute(Texte)

    If Matches.Count > 0 Then
        ExtraireInline = TrimComplet(Matches(0).SubMatches(0))
    Else
        ExtraireInline = "N/A"
    End If

    If ExtraireInline = "" Then ExtraireInline = "N/A"

End Function


' Essaie d'abord "libelle seul sur sa ligne", puis "libelle : valeur".
Public Function ChampSouple(Texte As String, TagDebut As String, TagFin As String) As String
    Dim v As String
    v = ExtraireEntreTags(Texte, TagDebut, TagFin)
    If v = "N/A" Or v = "" Then
        v = ExtraireInline(Texte, TagDebut)
    End If
    ChampSouple = v
End Function


' ==================================================================
'  UTILITAIRES
' ==================================================================

' Recherche recursive d'un sous-dossier par son nom.
Private Function TrouverDossier(Parent As Object, Nom As String) As Object

    Dim f As Object, trouve As Object

    On Error Resume Next
    Set trouve = Parent.Folders(Nom)
    On Error GoTo 0
    If Not trouve Is Nothing Then
        Set TrouverDossier = trouve
        Exit Function
    End If

    For Each f In Parent.Folders
        Set trouve = TrouverDossier(f, Nom)
        If Not trouve Is Nothing Then
            Set TrouverDossier = trouve
            Exit Function
        End If
    Next f

    Set TrouverDossier = Nothing

End Function


' Supprime espaces / tabulations / retours a la ligne en debut et fin.
Public Function TrimComplet(Texte As String) As String
    Dim T As String
    T = Texte
    Do While Len(T) > 0 And (Left(T, 1) = " " Or Left(T, 1) = vbTab Or Left(T, 1) = vbCr Or Left(T, 1) = vbLf)
        T = Mid(T, 2)
    Loop
    Do While Len(T) > 0 And (Right(T, 1) = " " Or Right(T, 1) = vbTab Or Right(T, 1) = vbCr Or Right(T, 1) = vbLf)
        T = Left(T, Len(T) - 1)
    Loop
    TrimComplet = T
End Function


' Met une valeur multi-lignes sur une seule ligne (pour tenir en cellule).
Public Function UneLigne(s As String) As String
    Dim T As String
    T = s
    T = Replace(T, vbCrLf, " ")
    T = Replace(T, vbCr, " ")
    T = Replace(T, vbLf, " ")
    T = Replace(T, vbTab, " ")
    Do While InStr(T, "  ") > 0
        T = Replace(T, "  ", " ")
    Loop
    T = Trim(T)
    If T = "" Then T = "N/A"
    UneLigne = T
End Function


' Duree (minutes) -> "hh:mn"
Public Function FormatDuree(minutes As Long) As String
    If minutes < 0 Then minutes = 0
    FormatDuree = Format(minutes \ 60, "00") & ":" & Format(minutes Mod 60, "00")
End Function


' Conversion de date robuste. Le format jj/mm/aaaa est analyse
' EXPLICITEMENT pour eviter toute ambiguite de parametres regionaux.
Public Function ConversionDate(Txt As String) As Date

    Dim s As String
    s = Trim(Txt)
    If s = "" Or StrComp(s, "N/A", vbTextCompare) = 0 Then
        ConversionDate = 0
        Exit Function
    End If

    ' Normalisation des heures FR : 14 h 30 / 14h30 -> 14:30 ; espace insecable
    s = Replace(s, ChrW(160), " ")
    s = Replace(s, " h ", ":", , , vbTextCompare)
    s = Replace(s, "h", ":", , , vbTextCompare)
    s = Replace(s, " " & ChrW(224) & " ", " ")
    Do While InStr(s, "  ") > 0
        s = Replace(s, "  ", " ")
    Loop
    s = Trim(s)
    If Right(s, 1) = ":" Then s = Left(s, Len(s) - 1)

    ' Analyse explicite jj/mm/aaaa [hh:mm[:ss]]
    Dim rx As Object
    Set rx = CreateObject("VBScript.RegExp")
    rx.Pattern = "(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
    If rx.Test(s) Then
        Dim m As Object
        Set m = rx.Execute(s)(0)
        Dim jj As Integer, mm As Integer, aa As Integer
        Dim hh As Integer, mi As Integer, ss As Integer
        jj = CInt(m.SubMatches(0))
        mm = CInt(m.SubMatches(1))
        aa = CInt(m.SubMatches(2))
        If aa < 100 Then aa = 2000 + aa
        hh = 0: mi = 0: ss = 0
        If m.SubMatches(3) <> "" Then hh = CInt(m.SubMatches(3))
        If m.SubMatches(4) <> "" Then mi = CInt(m.SubMatches(4))
        If m.SubMatches(5) <> "" Then ss = CInt(m.SubMatches(5))
        On Error Resume Next
        ConversionDate = DateSerial(aa, mm, jj) + TimeSerial(hh, mi, ss)
        If Err.Number <> 0 Then ConversionDate = 0
        On Error GoTo 0
        Exit Function
    End If

    ' Repli : conversion native
    If IsDate(s) Then
        ConversionDate = CDate(s)
    Else
        ConversionDate = 0
    End If

End Function
