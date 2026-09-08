# Dashboard design decisions

Subject: historical F1 race intelligence for a fan comparing weekends and competitors. Primary job: navigate a season into a readable weekend result and grid comparison.

Palette: pit-wall navy #122c50; paper blue #f3f6fa; timing blue #255fcc; sky signal #75bcf0; data ink #162c49; rule gray #d5dfeb. Typography: Barlow Condensed for race headings and round numbers, Barlow for tables and prose, tabular numerals for measurements. Fonts are bundled through npm, not remotely fetched.

Layout: wide season heading and selector, driver timing table beside constructors, then a two-column calendar. Race detail devotes most width to the timing table; secondary context stays in a narrow rail. Mobile stacks sections and gives wide tables their own horizontal scroll. The signature is actual race-round numbering integrated into weekend navigation. No invented telemetry, track outlines, or decorative dashboard metrics.

The initial alternative was a dark timing monitor with colored cards. It was rejected because repeated cards obscure rankings and a dark red/black treatment is less readable for dense academic data review. Blue and white retain a timing-table hierarchy with restrained motorsport typography. Data states explicitly separate missing records from request failures.
