' Shared details/browser labels; ready tracks take priority over download queue status.
function SubtitleSummaryFromTracks(data as object) as object
    result = {state:data.state,count:0,has_full:false,has_forced:false,has_sdh:false,languages:[]}
    if data.tracks = invalid then return result
    seen = {}
    for each track in data.tracks
        result.count++
        if track.kind = "forced"
            result.has_forced = true
        else
            result.has_full = true
        end if
        if track.kind = "sdh" then result.has_sdh = true
    end for
    for each track in data.tracks
        if track.kind <> "forced" or not result.has_full
            if track.language <> invalid
                if not seen.DoesExist(track.language)
                    seen[track.language] = true
                    result.languages.Push(track.language)
                end if
            end if
        end if
    end for
    return result
end function

function SubtitleIndicatorLabel(summary as dynamic, show = false as boolean) as string
    if summary = invalid then return "Subtitles: Checking availability"
    if show
        total = summary.episode_total
        available = summary.episodes_available
        full = summary.episodes_full
        if total = invalid or available = invalid or full = invalid then return "Subtitles: Checking availability"
        if available = 0
            if summary.episodes_converting <> invalid and summary.episodes_converting > 0 then return "Subtitles: Converting embedded tracks"
            if summary.episodes_with_embedded_images <> invalid and summary.episodes_with_embedded_images > 0 then return "Subtitles: Embedded tracks need conversion"
            return "Subtitles: None available yet"
        end if
        if full = total then return "Subtitles: All " + total.ToStr() + " episodes"
        if full = 0 then return "Subtitles: Forced only on " + available.ToStr() + " of " + total.ToStr() + " episodes"
        return "Subtitles: Full tracks on " + full.ToStr() + " of " + total.ToStr() + " episodes"
    end if
    if summary.count <> invalid
        if summary.count > 0
            if summary.has_full <> true then return "Subtitles: Forced only (selected dialogue)"
            language = ""
            if summary.languages <> invalid
                for each value in summary.languages
                    if value = "eng" then language = "English"
                end for
                if summary.languages.Count() > 1
                    if language <> "" then language += " + other languages"
                    if language = "" then language = "Multiple languages"
                else if summary.languages.Count() = 1 and language = ""
                    value = summary.languages[0]
                    if value = "spa" then language = "Spanish"
                    if value = "fre" then language = "French"
                    if value = "und" then language = "Unknown language"
                    if language = "" then language = UCase(value)
                end if
            end if
            result = "Subtitles: Available"
            if language <> "" then result += " · " + language
            if summary.has_sdh = true then result += " · SDH"
            return result
        end if
    end if
    if summary.conversion_pending = true or summary.state = "processing" then return "Subtitles: Converting embedded tracks"
    if summary.embedded_image_count <> invalid and summary.embedded_image_count > 0 then return "Subtitles: Embedded tracks need conversion"
    if summary.state = "pending" then return "Subtitles: Checking availability"
    if summary.state = "quota_wait" or summary.state = "rate_wait" then return "Subtitles: Not available yet · Download queued"
    if summary.state = "needs_review" then return "Subtitles: Not available · Match needs review"
    return "Subtitles: None available yet"
end function
