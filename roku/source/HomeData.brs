' Pure data adapter: new shelves can be added without changing focus or playback.
function MediaText(value as dynamic) as string
    if value = invalid then return ""
    if GetInterface(value, "ifString") <> invalid then return value.Trim()
    return ""
end function

function MediaNumber(value as dynamic) as float
    kind = Type(value)
    if kind = "Integer" or kind = "roInt" or kind = "Float" or kind = "roFloat" or kind = "Double" or kind = "roDouble" or kind = "LongInteger" or kind = "roLongInteger"
        return value * 1.0
    end if
    return 0.0
end function

function FirstMediaText(movie as object, keys as object) as string
    for each key in keys
        value = MediaText(movie[key])
        if value <> "" then return value
    end for
    return ""
end function

function RuntimeLabel(seconds as float) as string
    minutes = Int(seconds / 60)
    if minutes < 1 then return ""
    hours = Int(minutes / 60)
    remainder = minutes mod 60
    if hours = 0 then return minutes.ToStr() + "m"
    result = hours.ToStr() + "h"
    if remainder > 0 then result += " " + remainder.ToStr() + "m"
    return result
end function

function MoviePresentation(movie as object) as object
    duration = MediaNumber(movie.duration)
    if duration <= 0 then duration = MediaNumber(movie.runtime) * 60
    metadata = ""
    year = MediaNumber(movie.year)
    if year > 0 then metadata = Int(year).ToStr()
    runtime = RuntimeLabel(duration)
    if runtime <> ""
        if metadata <> "" then metadata += "  ·  "
        metadata += runtime
    end if
    if movie.kind = "show"
        seasonCount = Int(MediaNumber(movie.season_count))
        episodeCount = Int(MediaNumber(movie.episode_count))
        seasonWord = " seasons"
        episodeWord = " episodes"
        if seasonCount = 1 then seasonWord = " season"
        if episodeCount = 1 then episodeWord = " episode"
        metadata = seasonCount.ToStr() + seasonWord + "  ·  " + episodeCount.ToStr() + episodeWord
    end if
    landscape = FirstMediaText(movie, ["landscape_url", "thumbnail_url", "backdrop_url", "hero_url"])
    cardImage = landscape
    portrait = false
    if cardImage = ""
        cardImage = MediaText(movie.poster_url)
        portrait = cardImage <> ""
    end if
    if cardImage = "" then cardImage = "pkg:/images/card-fallback.png"
    heroImage = FirstMediaText(movie, ["backdrop_url", "hero_url", "landscape_url"])
    if heroImage = "" then heroImage = "pkg:/images/hero-fallback.png"
    description = FirstMediaText(movie, ["description", "overview"])
    position = MediaNumber(movie.resume_position)
    progress = 0.0
    if duration > 0 and position > 0 then progress = position / duration
    if progress > 1 then progress = 1
    return {
        title: movie.title, metadataLine: metadata, description: description
        cardImage: cardImage, portraitArt: portrait, heroImage: heroImage
        historySort:MediaText(movie.history_updated_at), progress: progress, movieData: movie
        addedSort: MediaText(movie.date_added), titleSort: LCase(movie.title)
        resumeSeconds: position, durationSeconds: duration
    }
end function

function BuildHomeRows(movies as object) as object
    allMovies = []
    shows = []
    recent = []
    continuing = []
    genreNames = []
    genreBuckets = {}
    for each movie in movies
        entry = MoviePresentation(movie)
        if movie.kind = "show"
            shows.Push(entry)
        else
            allMovies.Push(entry)
        end if
        recent.Push(entry)
        genres = movie.genres
        if Type(genres) <> "roArray" and Type(genres) <> "Array" then genres = []
        seen = {}
        for each value in genres
            name = MediaText(value)
            normalized = LCase(name)
            if name <> "" and not seen.DoesExist(normalized)
                seen[normalized] = true
                if not genreBuckets.DoesExist(normalized)
                    genreNames.Push({name: name, sortKey: normalized})
                    genreBuckets[normalized] = []
                end if
                genreBuckets[normalized].Push(entry)
            end if
        end for
        if seen.Count() = 0
            if not genreBuckets.DoesExist("uncategorized")
                genreNames.Push({name:"Uncategorized",sortKey:"uncategorized"})
                genreBuckets["uncategorized"] = []
            end if
            genreBuckets["uncategorized"].Push(entry)
        end if
        if movie.kind = "show" and movie.continue_watching = true
            continuing.Push(entry)
        else if entry.resumeSeconds > 0 and entry.durationSeconds > entry.resumeSeconds + 30
            if movie.completed <> true then continuing.Push(entry)
        end if
    end for
    continuing.SortBy("historySort", "r")
    allMovies.SortBy("titleSort")
    shows.SortBy("titleSort")
    recent.SortBy("addedSort", "r")
    rows = []
    if continuing.Count() > 0 then rows.Push({key: "continue", title: "Continue Watching", items: continuing})
    if recent.Count() > 0
        limited = []
        for i = 0 to recent.Count() - 1
            if i >= 24 then exit for
            limited.Push(recent[i])
        end for
        rows.Push({key: "recent", title: "Recently Added", items: limited})
        if shows.Count() > 0 then rows.Push({key: "shows", title: "TV Shows", items: shows})
        if allMovies.Count() > 0 then rows.Push({key: "all", title: "All Movies", items: allMovies})
    end if
    genreNames.SortBy("sortKey")
    for each genre in genreNames
        if genre.sortKey <> "uncategorized"
            items = genreBuckets[genre.sortKey]
            items.SortBy("titleSort")
            rows.Push({key: "genre:" + genre.sortKey, title: genre.name, items: items})
        end if
    end for
    if genreBuckets.DoesExist("uncategorized")
        items = genreBuckets["uncategorized"]
        items.SortBy("titleSort")
        rows.Push({key:"genre:uncategorized",title:"Uncategorized",items:items})
    end if
    return rows
end function
