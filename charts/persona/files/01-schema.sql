USE animal_persona;

CREATE TABLE persona (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    animal VARCHAR(25) NOT NULL UNIQUE,
    slug VARCHAR(25) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL,
    image_key VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE registrations (
    id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    age TINYINT UNSIGNED NOT NULL,
    persona_id INT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_age CHECK (age BETWEEN 1 AND 120),
    CONSTRAINT fk_registration_persona FOREIGN KEY (persona_id) REFERENCES persona(id)
) ENGINE=InnoDB;

INSERT INTO persona (animal, slug, description, image_key) VALUES
('Panda', 'panda', 'Calm under pressure, especially when someone else is doing the work.', 'panda.svg'),
('Fox', 'fox', 'Always has a clever solution, and occasionally caused the problem.', 'fox.svg'),
('Owl', 'owl', 'Thinks deeply. Usually after everyone else has gone to sleep.', 'owl.svg'),
('Lion', 'lion', 'Born to lead. Delegates everything except choosing lunch.', 'lion.svg'),
('Cat', 'cat', 'Independent thinker. Your meeting invitation is merely a suggestion.', 'cat.svg'),
('Dog', 'dog', 'Team player of the year. Celebrates every small win like a promotion.', 'dog.svg'),
('Rabbit', 'rabbit', 'Fast, curious, and somehow working on five side projects.', 'rabbit.svg'),
('Koala', 'koala', 'Protects work-life balance with the dedication of a full-time nap manager.', 'koala.svg');
