' Presentation helpers shared by the movie/episode and series title pages.
function TitleSummary(item as dynamic, limit = 420 as integer) as string
    if item = invalid then return "Summary not available yet."
    text = MediaText(item.description)
    if text = "" then text = MediaText(item.overview)
    if text = "" or text = "Choose a season or collection to browse." then return "Summary not available yet."
    if Len(text) > limit
        text = Left(text, limit)
        lastSpace = Instr(1, text, " ")
        for i = Len(text) to 1 step -1
            if Mid(text, i, 1) = " "
                lastSpace = i
                exit for
            end if
        end for
        if lastSpace > limit - 40 then text = Left(text, lastSpace - 1)
        text += "…"
    end if
    if item.kind = "episode" and item.description_scope = "series" then text = "Series overview: " + text
    return text
end function

function TitleCast(item as dynamic) as string
    if item = invalid then return ""
    names = item.cast
    if Type(names) <> "roArray" and Type(names) <> "Array" then return ""
    text = ""
    count = 0
    for each value in names
        name = MediaText(value)
        if name <> ""
            if text <> "" then text += ", "
            text += name
            count++
            if count >= 5 then exit for
        end if
    end for
    if text = "" then return ""
    prefix = "Starring: "
    if item.kind = "episode" and item.cast_scope = "series" then prefix = "Series cast: "
    return prefix + text
end function
