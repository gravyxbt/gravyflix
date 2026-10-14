' Pre-index once per library update; keystrokes never fetch or scan episode trees.
function SearchNormalize(value as dynamic) as string
    text = LCase(MediaText(value))
    folds = [ ["[àáâãäå]", "a"], ["[èéêë]", "e"], ["[ìíîï]", "i"], ["[òóôõö]", "o"], ["[ùúûü]", "u"], ["ñ", "n"], ["ç", "c"] ]
    for each fold in folds
        text = CreateObject("roRegex", fold[0], "").ReplaceAll(text, fold[1])
    end for
    text = CreateObject("roRegex", "&", "").ReplaceAll(text, " and ")
    text = CreateObject("roRegex", "['’]", "").ReplaceAll(text, "")
    text = CreateObject("roRegex", "[^a-z0-9]+", "").ReplaceAll(text, " ")
    return text.Trim()
end function

function SearchItemKey(item as object) as string
    id = item.id
    if GetInterface(id, "ifString") <> invalid then return id
    return id.ToStr()
end function

function BuildSearchIndex(movies as object) as object
    index = []
    seen = {}
    for each movie in movies
        if movie.kind <> "episode" and movie.id <> invalid
            key = SearchItemKey(movie)
            if not seen.DoesExist(key)
                seen[key] = true
                title = SearchNormalize(movie.title)
                cast = ""
                genres = ""
                for each field in ["cast", "genres"]
                    values = movie[field]
                    if Type(values) = "roArray" or Type(values) = "Array"
                        joined = ""
                        for each value in values
                            joined += " " + SearchNormalize(value)
                        end for
                        if field = "cast" then cast = joined
                        if field = "genres" then genres = joined
                    end if
                end for
                index.Push({key:key, title:title, titleSort:LCase(MediaText(movie.title)),
                    cast:cast, genres:genres, movieData:movie})
            end if
        end if
    end for
    index.SortBy("titleSort")
    return index
end function

function FindSearchMatches(index as object, query as string, limit = 150 as integer) as object
    normalized = SearchNormalize(Left(query, 75))
    result = {items:[], total:0, normalized:normalized}
    if normalized = "" then return result
    terms = normalized.Split(" ")
    ranked = []
    for each entry in index
        text = entry.title + " " + entry.cast + " " + entry.genres
        matches = true
        for each term in terms
            if term <> "" and Instr(1, text, term) = 0 then matches = false
        end for
        if matches
            ' Alphabetic ties within exact, prefix, title and metadata match groups.
            score = 3
            if Instr(1, entry.title, normalized) > 0 then score = 2
            if Left(entry.title, Len(normalized)) = normalized then score = 1
            if entry.title = normalized then score = 0
            ranked.Push({rank:score.ToStr() + ":" + entry.titleSort, entry:entry})
        end if
    end for
    ranked.SortBy("rank")
    result.total = ranked.Count()
    for each hit in ranked
        if result.items.Count() >= limit then exit for
        result.items.Push(hit.entry.movieData)
    end for
    return result
end function
