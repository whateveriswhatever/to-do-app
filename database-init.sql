create table Accounts(
    ID int generated always as identity primary key,
    username varchar(55) not null,
    password varchar(55) not null
);

create table Tasks (
    ID int primary key not null,
    order_priority int generated always default 0,
    content varchar(444) not null,
    accountID int not null,

    constraint fk_userAccount
        foreign key accountID references Accounts(ID)
        on delete cascade
);